from __future__ import annotations

import hashlib
import json

from backend.schemas.workspace import BpmnModelResponse
from backend.schemas.simulation import CreateSimulationRunRequest
from backend.security import get_current_tenant_id, set_current_tenant_id
from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation
from backend.simulation.result_parser import with_output_files
from backend.simulation.scenario_builder import build_prosimos_scenario
from backend.simulation.storage import (
    complete_simulation_run,
    create_simulation_run,
    fail_simulation_run,
    find_active_run_by_key,
)


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

    scenario = build_prosimos_scenario(bpmn_xml=bpmn_xml, request=request)

    idempotency_key = request.idempotency_key or _derive_idempotency_key(
        bpmn_model_id=bpmn_model.id,
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
    )

    existing = find_active_run_by_key(
        bpmn_model_id=bpmn_model.id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return existing, None, bpmn_xml

    run = create_simulation_run(
        bpmn_model_id=bpmn_model.id,
        process_id=bpmn_model.process_id,
        scenario_name=request.scenario_name.strip() or "Baseline AS-IS",
        request=request,
        scenario=scenario,
        idempotency_key=idempotency_key,
    )
    return run, scenario, bpmn_xml


async def execute_simulation_run(
    *,
    run_id: int,
    tenant_id: str,
    bpmn_xml: str,
    scenario: ProsimosScenario,
    request: CreateSimulationRunRequest,
) -> dict:
    set_current_tenant_id(tenant_id)
    try:
        result = with_output_files(
            await run_prosimos_simulation(
                ProsimosSimulationRequest(
                    bpmn_xml=bpmn_xml,
                    scenario=scenario,
                    total_cases=request.total_cases,
                    start_date=request.start_date,
                )
            )
        )
    except ProsimosError as exc:
        return fail_simulation_run(run_id=run_id, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - never leave a run stuck in "pending"
        return fail_simulation_run(run_id=run_id, error=f"Errore inatteso: {exc}")

    return complete_simulation_run(run_id=run_id, result=result)


async def create_and_run_simulation(
    *,
    bpmn_model: BpmnModelResponse,
    request: CreateSimulationRunRequest,
) -> dict:
    """Synchronous helper kept for tests and non-HTTP callers."""
    run, scenario, bpmn_xml = prepare_simulation_run(
        bpmn_model=bpmn_model, request=request
    )
    if scenario is None:
        return run

    return await execute_simulation_run(
        run_id=run["id"],
        tenant_id=get_current_tenant_id(),
        bpmn_xml=bpmn_xml,
        scenario=scenario,
        request=request,
    )
