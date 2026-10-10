from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import object_session

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.schemas.simulation_model import CreateSimulationModelRunRequest
from backend.security import get_current_tenant_id
from backend.settings import settings
from backend.simulation.models import ProsimosScenario, ProsimosSimulationResult
from backend.simulation.queue import LEGACY_STALE_RUN_ERROR, admit, hold_queue, queue_view, reap_stale_runs
from backend.workspace_storage import (
    WorkspaceSimulationRun,
    WorkspaceSimulationRunArtifact,
    WorkspaceSimulationRunLog,
    workspace_connection,
)


logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# La scadenza dei run morti ora la decide la coda (P0.3): battito, non eta'.
STALE_RUN_ERROR = LEGACY_STALE_RUN_ERROR


def simulation_run_to_dict(
    run: WorkspaceSimulationRun,
    *,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": run.id,
        "bpmn_model_id": run.bpmn_model_id,
        "process_id": run.process_id,
        "scenario_name": run.scenario_name,
        "engine": run.engine,
        "status": run.status,
        "idempotency_key": run.idempotency_key,
        "request": json.loads(run.request_json or "{}"),
        "scenario": json.loads(run.scenario_json or "{}"),
        "result": json.loads(run.result_json or "{}"),
        "outputs": json.loads(run.outputs_json or "[]"),
        # Full-log KPI summary (from the artifact table). Small — always included
        # so run cards / detail can show KPIs without fetching the replay blob.
        "summary": summary,
        "error": run.error,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        # In coda (con la posizione) o in corso: cosa dire al consulente mentre aspetta.
        "queue": view.model_dump() if (session := object_session(run)) is not None and (view := queue_view(session, run)) else None,
    }


def find_active_run_by_key(
    *,
    bpmn_model_id: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Return an in-flight (pending) run with the same key, if any."""
    with workspace_connection() as session:
        # Prima di dire "ce n'e' gia' uno in volo": uno senza battito non lo e'.
        reap_stale_runs(session)
        run = session.execute(
            select(WorkspaceSimulationRun)
            .where(WorkspaceSimulationRun.tenant_id == get_current_tenant_id())
            .where(WorkspaceSimulationRun.bpmn_model_id == bpmn_model_id)
            .where(WorkspaceSimulationRun.idempotency_key == idempotency_key)
            .where(WorkspaceSimulationRun.status == "pending")
            .order_by(WorkspaceSimulationRun.id.desc())
        ).scalars().first()
        return simulation_run_to_dict(run) if run is not None else None


def create_simulation_run(
    *,
    bpmn_model_id: str,
    process_id: str,
    scenario_name: str,
    request: CreateSimulationRunRequest | CreateSimulationModelRunRequest,
    scenario: ProsimosScenario,
    idempotency_key: str | None = None,
    bpmn_xml: str | None = None,
) -> dict[str, Any]:
    """Il run entra in coda; ``SimulationQueueFull`` se la coda e' piena."""
    with workspace_connection() as session:
        admit(session)
        run = _new_run(
            bpmn_model_id=bpmn_model_id,
            process_id=process_id,
            scenario_name=scenario_name,
            request=request,
            scenario=scenario,
            idempotency_key=idempotency_key,
            bpmn_xml=bpmn_xml,
        )
        session.add(run)
        session.flush()
        return simulation_run_to_dict(run)


def create_simulation_run_group(
    *,
    bpmn_model_id: str,
    process_id: str,
    members: list[tuple[CreateSimulationRunRequest, ProsimosScenario, str, str]],
) -> list[dict[str, Any]]:
    """Un gruppo di ripetizioni (SIM-04) in coda, tutto in una transazione.

    ``members``: (richiesta, scenario, chiave di idempotenza, BPMN) di ognuna.
    Se il gruppo e' gia' in volo (lo stesso invio, ritentato) restituisce
    quello: il controllo sta sotto il lock della coda, quindi due invii insieme
    non creano due gruppi. Coda piena: non entra nessuna ripetizione.
    """
    keys = [key for _, _, key, _ in members]
    with workspace_connection() as session:
        hold_queue(session)
        reap_stale_runs(session)
        existing = session.execute(
            select(WorkspaceSimulationRun)
            .where(WorkspaceSimulationRun.tenant_id == get_current_tenant_id())
            .where(WorkspaceSimulationRun.bpmn_model_id == bpmn_model_id)
            .where(WorkspaceSimulationRun.idempotency_key.in_(keys))
            .where(WorkspaceSimulationRun.status == "pending")
        ).scalars().all()
        if existing:
            order = {key: index for index, key in enumerate(keys)}
            return [simulation_run_to_dict(run) for run in sorted(existing, key=lambda r: order[r.idempotency_key])]
        admit(session, runs=len(members))
        runs = [
            _new_run(
                bpmn_model_id=bpmn_model_id,
                process_id=process_id,
                scenario_name=request.scenario_name,
                request=request,
                scenario=scenario,
                idempotency_key=key,
                bpmn_xml=bpmn_xml,
            )
            for request, scenario, key, bpmn_xml in members
        ]
        session.add_all(runs)
        session.flush()
        return [simulation_run_to_dict(run) for run in runs]


def _new_run(
    *,
    bpmn_model_id: str,
    process_id: str,
    scenario_name: str,
    request: CreateSimulationRunRequest | CreateSimulationModelRunRequest,
    scenario: ProsimosScenario,
    idempotency_key: str | None,
    bpmn_xml: str | None,
) -> WorkspaceSimulationRun:
    return WorkspaceSimulationRun(
        tenant_id=get_current_tenant_id(),
        bpmn_model_id=bpmn_model_id,
        process_id=process_id,
        scenario_name=scenario_name,
        engine="prosimos",
        status="pending",
        idempotency_key=idempotency_key,
        request_json=request.model_copy(
            update={"current_bpmn_xml": None}
        ).model_dump_json(),
        scenario_json=json.dumps(scenario.payload, ensure_ascii=False),
        model_json=json.dumps(scenario.model, ensure_ascii=False) if scenario.model is not None else None,
        result_json="{}",
        outputs_json="[]",
        error=None,
        created_at=now_iso(),
        completed_at=None,
        # Il run entra in coda con il BPMN normalizzato: chiunque lo prenda lo esegue.
        bpmn_xml=bpmn_xml,
        attempts=0,
    )


def complete_simulation_run(
    *,
    run_id: int,
    result: ProsimosSimulationResult,
    summary: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    log_csv: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    run = _update_simulation_run(
        run_id=run_id,
        status="completed",
        result=result,
        error=None,
        worker_id=worker_id,
    )
    # Il risultato puo' essere stato scartato perche' arrivato dopo la chiusura:
    # in quel caso non deve lasciare dietro di se' nemmeno l'artefatto.
    if run["status"] == "completed" and (summary is not None or replay is not None):
        _write_simulation_artifact(run_id=run_id, summary=summary or {}, replay=replay or {})
        run["summary"] = summary
    if run["status"] == "completed" and log_csv:
        _write_simulation_log(run_id=run_id, log_csv=log_csv)
    return run


def _write_simulation_log(*, run_id: int, log_csv: str) -> None:
    with workspace_connection() as session:
        existing = session.get(WorkspaceSimulationRunLog, run_id)
        if existing is None:
            session.add(
                WorkspaceSimulationRunLog(
                    run_id=run_id,
                    tenant_id=get_current_tenant_id(),
                    log_csv=log_csv,
                    created_at=now_iso(),
                )
            )
        else:
            existing.log_csv = log_csv
        session.flush()


def get_simulation_log_csv(run_id: int) -> str | None:
    """Il CSV del motore di un run del tenant corrente; ``None`` se non c'e'."""
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return None
        row = session.get(WorkspaceSimulationRunLog, run_id)
        return row.log_csv if row is not None else None


def _write_simulation_artifact(
    *,
    run_id: int,
    summary: dict[str, Any],
    replay: dict[str, Any],
) -> None:
    with workspace_connection() as session:
        existing = session.get(WorkspaceSimulationRunArtifact, run_id)
        if existing is None:
            session.add(
                WorkspaceSimulationRunArtifact(
                    run_id=run_id,
                    tenant_id=get_current_tenant_id(),
                    replay_schema_version=settings.sim_replay_schema_version,
                    summary_json=json.dumps(summary, ensure_ascii=False),
                    replay_json=json.dumps(replay, ensure_ascii=False),
                    created_at=now_iso(),
                )
            )
        else:
            existing.replay_schema_version = settings.sim_replay_schema_version
            existing.summary_json = json.dumps(summary, ensure_ascii=False)
            existing.replay_json = json.dumps(replay, ensure_ascii=False)
        session.flush()


def get_simulation_replay(run_id: int) -> dict[str, Any] | None:
    """The heavy display artifact — fetched only by the replay endpoint."""
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return None
        artifact = session.get(WorkspaceSimulationRunArtifact, run_id)
        if artifact is None:
            return None
        return {
            "schema_version": artifact.replay_schema_version,
            "replay": json.loads(artifact.replay_json or "{}"),
        }


def get_simulation_run_model(run_id: int) -> tuple[bool, dict[str, Any] | None]:
    """Il modello IR che il run ha simulato.

    ``(False, None)``: il run non c'e' (o e' di un altro tenant).
    ``(True, None)``: il run c'e' ma e' anteriore alla 0033 e il modello non
    e' stato conservato.
    """
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return False, None
        return True, json.loads(run.model_json) if run.model_json else None


def _summary_for(session, run_id: int) -> dict[str, Any] | None:
    artifact = session.get(WorkspaceSimulationRunArtifact, run_id)
    if artifact is None:
        return None
    return json.loads(artifact.summary_json or "{}") or None


def fail_simulation_run(*, run_id: int, error: str, worker_id: str | None = None) -> dict[str, Any]:
    return _update_simulation_run(
        run_id=run_id,
        status="failed",
        result=ProsimosSimulationResult(),
        error=error,
        worker_id=worker_id,
    )


def get_simulation_run(run_id: int) -> dict[str, Any] | None:
    with workspace_connection() as session:
        # E' la rotta che il frontend interroga ogni pochi secondi: e' qui che
        # una simulazione morta deve smettere di sembrare viva.
        reap_stale_runs(session)
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return None
        return simulation_run_to_dict(run, summary=_summary_for(session, run_id))


def list_simulation_runs(bpmn_model_id: str) -> list[dict[str, Any]]:
    with workspace_connection() as session:
        reap_stale_runs(session)
        rows = session.execute(
            select(WorkspaceSimulationRun)
            .where(WorkspaceSimulationRun.tenant_id == get_current_tenant_id())
            .where(WorkspaceSimulationRun.bpmn_model_id == bpmn_model_id)
            .order_by(WorkspaceSimulationRun.id.desc())
        ).scalars().all()
        return [
            simulation_run_to_dict(row, summary=_summary_for(session, row.id))
            for row in rows
        ]


def _update_simulation_run(
    *,
    run_id: int,
    status: str,
    result: ProsimosSimulationResult,
    error: str | None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            raise ValueError(f"Simulation run non trovata: {run_id}")

        # Un esecutore dato per morto, il cui run e' tornato in coda o e' di un
        # altro, consegna tardi: il suo esito non vale piu'.
        # Un run gia' preso accetta l'esito solo dal suo esecutore.
        stolen = run.started_at is not None and (worker_id is None or run.worker_id != worker_id)
        if run.status != "pending" or stolen:
            # Arriva un risultato per una simulazione gia' chiusa: quasi sempre
            # una che avevamo dichiarato morta e che invece stava ancora
            # girando. Scriverlo adesso la riporterebbe in vita dopo che il
            # consulente ne ha gia' lanciata un'altra, e cancellerebbe la frase
            # che spiega cosa era successo.
            logger.warning(
                "risultato tardivo per la simulazione %s, gia' %s: scartato",
                run_id,
                run.status,
            )
            return simulation_run_to_dict(run, summary=_summary_for(session, run_id))

        run.status = status
        run.result_json = json.dumps(result.payload, ensure_ascii=False)
        run.outputs_json = json.dumps(result.outputs, ensure_ascii=False)
        run.error = error
        run.completed_at = now_iso()
        session.flush()
        return simulation_run_to_dict(run)
