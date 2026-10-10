from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from backend.eventlog.export import Exported, to_csv, to_xes
from backend.eventlog.synthetic import from_prosimos_csv
from backend.schemas.workspace import BpmnModelResponse
from backend.schemas.simulation import CreateSimulationRunRequest
from backend.schemas.simulation_model import CreateSimulationModelRunRequest
from backend.security import set_current_tenant_id
from backend.schemas.simulation import ScenarioProvenanceResponse, ScenarioTemplateResponse
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.provenance import build_scenario_provenance
from backend.simulation.log_processor import (
    activity_name_to_element_id,
    process_prosimos_log,
)
from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation
from backend.simulation.queue import ClaimedRun, SimulationQueueFull, beat, claim_next_run
from backend.simulation.result_parser import with_output_files
from backend.simulation.ir.model import SimulationModel
from backend.simulation.ir.patch import apply_patch
from backend.simulation.scenario_builder import (
    baseline_for_bpmn,
    build_prosimos_scenario,
    build_prosimos_scenario_from_model,
    describe_scenario_template,
)
from backend.settings import settings
from backend.simulation.storage import (
    complete_simulation_run,
    create_simulation_run,
    fail_simulation_run,
    find_active_run_by_key,
    get_simulation_log_csv,
    get_simulation_run,
)


RunRequest = CreateSimulationRunRequest | CreateSimulationModelRunRequest

logger = logging.getLogger(__name__)


class SimulationCapacityError(RuntimeError):
    """La coda delle simulazioni e' piena adesso, non e' un errore della richiesta.

    Serve un tipo suo perche' la rotta deve rispondere 429 e non 400: la stessa
    richiesta, fra qualche minuto, funziona.
    """


def _derive_idempotency_key(
    *,
    bpmn_model_id: str,
    bpmn_xml: str,
    scenario: ProsimosScenario,
    request: CreateSimulationRunRequest,
) -> str:
    material = json.dumps(
        {
            "bpmn_model_id": bpmn_model_id,
            "bpmn_xml": bpmn_xml,
            "scenario": scenario.payload,
            "total_cases": request.total_cases,
            "start_date": request.start_date,
            "arrival_interval_seconds": request.arrival_interval_seconds,
            "default_task_duration_seconds": request.default_task_duration_seconds,
            "default_cost_per_hour": request.default_cost_per_hour,
            "resource_amount": request.resource_amount,
            "resource_name": request.resource_name,
            # Stesso scenario, seed diverso: un altro campione, un altro run.
            "seed": request.seed,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def scenario_template_for_model(
    *,
    bpmn_model: BpmnModelResponse,
    current_bpmn_xml: str | None,
) -> ScenarioTemplateResponse:
    """Tasks + branching gateways the frontend can build a per-element form from.

    The BPMN is normalised first so the element ids match those the run will
    actually simulate."""
    bpmn_xml = (current_bpmn_xml or bpmn_model.xml or "").strip()
    if not bpmn_xml:
        raise ValueError("Salva o genera un BPMN prima di configurare la simulazione.")
    return describe_scenario_template(normalize_bpmn_for_prosimos(bpmn_xml), source_bpmn_xml=bpmn_xml)


def scenario_provenance_for_model(
    *,
    bpmn_model: BpmnModelResponse,
    current_bpmn_xml: str | None,
) -> ScenarioProvenanceResponse:
    """Per-element structural provenance for the scenario builder — sourced from
    the approved BPMN review's process-understanding artifact."""
    return build_scenario_provenance(
        bpmn_model_id=bpmn_model.id,
        current_bpmn_xml=current_bpmn_xml,
        stored_bpmn_xml=bpmn_model.xml,
    )


def simulation_model_for_bpmn(
    *,
    bpmn_model: BpmnModelResponse,
    current_bpmn_xml: str | None,
) -> SimulationModel:
    """La baseline IR del processo, sugli id del BPMN che il run simulera'."""
    bpmn_xml = (current_bpmn_xml or bpmn_model.xml or "").strip()
    if not bpmn_xml:
        raise ValueError("Salva o genera un BPMN prima di configurare la simulazione.")
    return baseline_for_bpmn(normalize_bpmn_for_prosimos(bpmn_xml), source_bpmn_xml=bpmn_xml)


def prepare_simulation_model_run(
    *,
    bpmn_model: BpmnModelResponse,
    request: CreateSimulationModelRunRequest,
) -> tuple[dict, ProsimosScenario | None, str]:
    """Come ``prepare_simulation_run``, per un run descritto dall'IR (SIM-37).

    Il modello e' quello della richiesta, oppure la baseline del BPMN con la
    patch applicata, oppure la baseline cosi' com'e'.
    """
    source_xml = (request.current_bpmn_xml or bpmn_model.xml or "").strip()
    if not source_xml:
        raise ValueError("Salva o genera un BPMN prima di avviare Prosimos.")
    bpmn_xml = normalize_bpmn_for_prosimos(source_xml)

    if request.model is not None:
        model = request.model
    else:
        model = baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source_xml)
        if request.patch is not None:
            model = apply_patch(model, request.patch)

    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn_xml, model=model)
    idempotency_key = request.idempotency_key or _derive_model_idempotency_key(
        bpmn_model_id=bpmn_model.id,
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
    )
    return _register_run(
        bpmn_model=bpmn_model,
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
        idempotency_key=idempotency_key,
    )


def _derive_model_idempotency_key(
    *,
    bpmn_model_id: str,
    bpmn_xml: str,
    scenario: ProsimosScenario,
    request: CreateSimulationModelRunRequest,
) -> str:
    # Lo scenario compilato contiene gia' tutto il modello: due richieste che
    # arrivano allo stesso JSON (modello intero o patch) sono lo stesso run.
    material = json.dumps(
        {
            "contract": "ir",
            "bpmn_model_id": bpmn_model_id,
            "bpmn_xml": bpmn_xml,
            "scenario": scenario.payload,
            "total_cases": request.total_cases,
            "start_date": request.start_date,
            "seed": request.seed,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def prepare_simulation_run(
    *,
    bpmn_model: BpmnModelResponse,
    request: CreateSimulationRunRequest,
) -> tuple[dict, ProsimosScenario | None, str]:
    """Create (or reuse) a pending run record.

    Returns (run, scenario, bpmn_xml). When the run is being reused because an
    identical simulation is still in flight, scenario is None and the caller
    must not launch execution.
    """
    bpmn_xml = (request.current_bpmn_xml or bpmn_model.xml or "").strip()
    if not bpmn_xml:
        raise ValueError("Salva o genera un BPMN prima di avviare Prosimos.")

    # Adapt the model to Prosimos' constraints (e.g. single end event) before it
    # feeds both the scenario and the engine request.
    bpmn_xml = normalize_bpmn_for_prosimos(bpmn_xml)

    scenario = build_prosimos_scenario(bpmn_xml=bpmn_xml, request=request)

    idempotency_key = request.idempotency_key or _derive_idempotency_key(
        bpmn_model_id=bpmn_model.id,
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
    )
    return _register_run(
        bpmn_model=bpmn_model,
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
        idempotency_key=idempotency_key,
    )


def _register_run(
    *,
    bpmn_model: BpmnModelResponse,
    bpmn_xml: str,
    scenario: ProsimosScenario,
    request: RunRequest,
    idempotency_key: str,
) -> tuple[dict, ProsimosScenario | None, str]:
    existing = find_active_run_by_key(
        bpmn_model_id=bpmn_model.id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return existing, None, bpmn_xml

    # Il run entra nella coda su Postgres (P0.3) e aspetta il suo turno: il
    # consulente vede la sua posizione invece di un rifiuto. Solo una coda
    # piena rifiuta, perche' oltre quella l'attesa non sarebbe un servizio.
    try:
        run = create_simulation_run(
            bpmn_model_id=bpmn_model.id,
            process_id=bpmn_model.process_id,
            scenario_name=request.scenario_name.strip() or "Baseline AS-IS",
            request=request,
            scenario=scenario,
            idempotency_key=idempotency_key,
            bpmn_xml=bpmn_xml,
        )
    except SimulationQueueFull as exc:
        raise SimulationCapacityError(str(exc)) from exc
    return run, scenario, bpmn_xml


def new_worker_id() -> str:
    """Chi esegue: host, processo e un suffisso, per riconoscerlo nei log e nel DB."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


async def drain_simulation_queue(worker_id: str | None = None) -> int:
    """Prende ed esegue run dalla coda finche' ce ne sono e il motore ha posto.

    Gira dopo ogni richiesta di run (BackgroundTask) e nel worker periodico: due
    drenaggi insieme sono sicuri, perche' la presa e' esclusiva. Restituisce
    quanti run ha eseguito.
    """
    worker_id = worker_id or new_worker_id()
    done = 0
    while (claimed := await asyncio.to_thread(claim_next_run, worker_id)) is not None:
        await execute_claimed_run(claimed)
        done += 1
    return done


async def execute_claimed_run(claimed: ClaimedRun) -> dict:
    """Esegue un run preso dalla coda, battendo finche' gira."""
    set_current_tenant_id(claimed.tenant_id)
    heart = asyncio.create_task(_keep_beating(claimed))
    try:
        result = with_output_files(
            await run_prosimos_simulation(
                ProsimosSimulationRequest(
                    bpmn_xml=claimed.bpmn_xml,
                    scenario=claimed.scenario,
                    total_cases=claimed.total_cases,
                    start_date=claimed.start_date,
                    seed=claimed.seed,
                )
            )
        )
    except ProsimosError as exc:
        return await asyncio.to_thread(fail_simulation_run, run_id=claimed.run_id, error=str(exc), worker_id=claimed.worker_id)
    except Exception as exc:  # noqa: BLE001 - never leave a run stuck in "pending"
        logger.exception("simulazione %s: errore inatteso", claimed.run_id)
        return await asyncio.to_thread(
            fail_simulation_run, run_id=claimed.run_id, error=f"Errore inatteso: {exc}", worker_id=claimed.worker_id
        )
    finally:
        heart.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heart

    # Lettura del log e scrittura in DB sono sincrone: fuori dall'event loop.
    summary, replay = await asyncio.to_thread(
        _process_event_log, result, bpmn_xml=claimed.bpmn_xml, scenario=claimed.scenario
    )
    return await asyncio.to_thread(
        complete_simulation_run,
        run_id=claimed.run_id,
        result=result,
        summary=summary,
        replay=replay,
        log_csv=getattr(result, "event_log_csv", None),
        worker_id=claimed.worker_id,
    )


async def _keep_beating(claimed: ClaimedRun) -> None:
    while True:
        await asyncio.sleep(settings.simulation_heartbeat_seconds)
        try:
            alive = await asyncio.to_thread(beat, claimed.run_id, claimed.worker_id)
        except SQLAlchemyError:  # un battito perso non ferma la simulazione
            logger.warning("simulazione %s: battito non scritto", claimed.run_id, exc_info=True)
            continue
        if not alive:
            # Il run non e' piu' nostro: l'esito, quando arriva, verra' scartato.
            return


def _process_event_log(
    result,
    *,
    bpmn_xml: str,
    scenario: ProsimosScenario,
) -> tuple[dict | None, dict | None]:
    """Turn the Prosimos event log into the run summary + replay artifact.
    Never raises — a log/parse failure just means no artifact for this run."""
    csv_text = getattr(result, "event_log_csv", None)
    if not csv_text:
        return None, None
    try:
        return process_prosimos_log(
            csv_text,
            normalized_bpmn_xml=bpmn_xml,
            scenario_payload=scenario.payload,
            prosimos_stats=result.payload,
            name_to_element_id=activity_name_to_element_id(bpmn_xml),
        )
    except Exception:  # noqa: BLE001 - the replay artifact is best-effort
        return None, None


async def create_and_run_simulation(
    *,
    bpmn_model: BpmnModelResponse,
    request: CreateSimulationRunRequest,
) -> dict:
    """Mette il run in coda e drena la coda: per i test e chi non passa da HTTP."""
    run, scenario, _ = prepare_simulation_run(bpmn_model=bpmn_model, request=request)
    if scenario is None:
        return run
    await drain_simulation_queue()
    return get_simulation_run(run["id"]) or run


class SimulationLogUnavailable(LookupError):
    """Il run non esiste, o non ha un log da esportare (fallito, o anteriore a SIM-06)."""


@dataclass(frozen=True, slots=True)
class SimulationLogExport:
    run_id: int
    seed: int | None
    engine_version: str | None
    file: Exported


def export_simulation_event_log(run_id: int, fmt: Literal["csv", "xes"]) -> SimulationLogExport:
    """Il log sintetico di un run come event log canonico, in CSV o XES."""
    run = get_simulation_run(run_id)
    csv_text = get_simulation_log_csv(run_id) if run is not None else None
    if run is None or not csv_text:
        raise SimulationLogUnavailable("Nessun log di eventi per questa simulazione.")

    result = run.get("result") or {}
    seed = result.get("Seed")
    engine_version = result.get("EngineVersion")
    log = from_prosimos_csv(csv_text, source_name=f"simulation-run-{run_id}")
    if fmt == "xes":
        metadata: dict[str, str | int] = {"deliR:runId": run_id}
        if seed is not None:
            metadata["deliR:seed"] = seed
        if engine_version:
            metadata["deliR:engineVersion"] = str(engine_version)
        exported = to_xes(log, metadata=metadata)
    else:
        exported = to_csv(log)
    return SimulationLogExport(run_id=run_id, seed=seed, engine_version=engine_version, file=exported)
