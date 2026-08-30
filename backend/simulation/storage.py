from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.security import get_current_tenant_id
from backend.simulation.models import ProsimosScenario, ProsimosSimulationResult
from backend.workspace_storage import WorkspaceSimulationRun, workspace_connection


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def simulation_run_to_dict(run: WorkspaceSimulationRun) -> dict[str, Any]:
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
        "error": run.error,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


def find_active_run_by_key(
    *,
    bpmn_model_id: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Return an in-flight (pending) run with the same key, if any."""
    with workspace_connection() as session:
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
    request: CreateSimulationRunRequest,
    scenario: ProsimosScenario,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    with workspace_connection() as session:
        run = WorkspaceSimulationRun(
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
            result_json="{}",
            outputs_json="[]",
            error=None,
            created_at=now_iso(),
            completed_at=None,
        )
        session.add(run)
        session.flush()
        return simulation_run_to_dict(run)


def complete_simulation_run(
    *,
    run_id: int,
    result: ProsimosSimulationResult,
) -> dict[str, Any]:
    return _update_simulation_run(
        run_id=run_id,
        status="completed",
        result=result,
        error=None,
    )


def fail_simulation_run(*, run_id: int, error: str) -> dict[str, Any]:
    return _update_simulation_run(
        run_id=run_id,
        status="failed",
        result=ProsimosSimulationResult(),
        error=error,
    )


def get_simulation_run(run_id: int) -> dict[str, Any] | None:
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return None
        return simulation_run_to_dict(run)


def list_simulation_runs(bpmn_model_id: str) -> list[dict[str, Any]]:
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceSimulationRun)
            .where(WorkspaceSimulationRun.tenant_id == get_current_tenant_id())
            .where(WorkspaceSimulationRun.bpmn_model_id == bpmn_model_id)
            .order_by(WorkspaceSimulationRun.id.desc())
        ).scalars().all()
        return [simulation_run_to_dict(row) for row in rows]


def _update_simulation_run(
    *,
    run_id: int,
    status: str,
    result: ProsimosSimulationResult,
    error: str | None,
) -> dict[str, Any]:
    with workspace_connection() as session:
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            raise ValueError(f"Simulation run non trovata: {run_id}")

        run.status = status
        run.result_json = json.dumps(result.payload, ensure_ascii=False)
        run.outputs_json = json.dumps(result.outputs, ensure_ascii=False)
        run.error = error
        run.completed_at = now_iso()
        session.flush()
        return simulation_run_to_dict(run)
