from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.security import get_current_tenant_id
from backend.settings import settings
from backend.simulation.models import ProsimosScenario, ProsimosSimulationResult
from backend.workspace_storage import (
    WorkspaceSimulationRun,
    WorkspaceSimulationRunArtifact,
    workspace_connection,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


#: Quanto si aspetta oltre il tempo massimo di Prosimos prima di dire che una
#: simulazione non tornera'. Il margine copre il tempo di scrittura del
#: risultato, non una seconda attesa.
STALE_RUN_MARGIN_SECONDS = 120.0

#: Cosa legge il consulente al posto di una rotella che gira per sempre.
STALE_RUN_ERROR = (
    "La simulazione non e' arrivata in fondo: il servizio si e' fermato mentre "
    "girava. Rilanciala."
)


def _started_at(created_at: str | None) -> datetime | None:
    if not created_at:
        return None
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _expire_stale_runs(session) -> list[int]:
    """Chiude le simulazioni rimaste `pending` oltre il tempo massimo.

    Una simulazione gira in un `BackgroundTasks` dello stesso processo: un
    riavvio o un crash a meta' la lascia `pending` in database, e da quel
    momento due cose non succedono piu'. La prima e' che nessuno la fallisce,
    quindi il frontend continua a chiedere il suo stato ogni cinque secondi,
    per sempre. La seconda, peggiore, e' che l'idempotenza vede ancora un run
    "in volo" con quella chiave e rifiuta di rilanciare lo scenario: un crash
    rende quello scenario non simulabile, e nessun messaggio lo dice.

    Returns:
        list[int]: Gli id chiusi adesso. Vuota quando non c'era niente di
            scaduto, che e' il caso normale.
    """
    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.prosimos_timeout_seconds + STALE_RUN_MARGIN_SECONDS
    )
    pending = session.execute(
        select(WorkspaceSimulationRun)
        .where(WorkspaceSimulationRun.tenant_id == get_current_tenant_id())
        .where(WorkspaceSimulationRun.status == "pending")
    ).scalars().all()

    expired: list[int] = []
    for run in pending:
        started = _started_at(run.created_at)
        # Una data illeggibile e' gia' un run che nessuno puo' giudicare vivo.
        if started is not None and started > cutoff:
            continue
        run.status = "failed"
        run.error = STALE_RUN_ERROR
        run.completed_at = now_iso()
        expired.append(run.id)

    if expired:
        session.flush()
    return expired


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
    }


def find_active_run_by_key(
    *,
    bpmn_model_id: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Return an in-flight (pending) run with the same key, if any."""
    with workspace_connection() as session:
        # Prima di dire "ce n'e' gia' uno in volo": uno scaduto non e' in volo.
        _expire_stale_runs(session)
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
    summary: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = _update_simulation_run(
        run_id=run_id,
        status="completed",
        result=result,
        error=None,
    )
    if summary is not None or replay is not None:
        _write_simulation_artifact(run_id=run_id, summary=summary or {}, replay=replay or {})
        run["summary"] = summary
    return run


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


def _summary_for(session, run_id: int) -> dict[str, Any] | None:
    artifact = session.get(WorkspaceSimulationRunArtifact, run_id)
    if artifact is None:
        return None
    return json.loads(artifact.summary_json or "{}") or None


def fail_simulation_run(*, run_id: int, error: str) -> dict[str, Any]:
    return _update_simulation_run(
        run_id=run_id,
        status="failed",
        result=ProsimosSimulationResult(),
        error=error,
    )


def get_simulation_run(run_id: int) -> dict[str, Any] | None:
    with workspace_connection() as session:
        # E' la rotta che il frontend interroga ogni cinque secondi: e' qui che
        # una simulazione morta deve smettere di sembrare viva.
        _expire_stale_runs(session)
        run = session.get(WorkspaceSimulationRun, run_id)
        if run is None or run.tenant_id != get_current_tenant_id():
            return None
        return simulation_run_to_dict(run, summary=_summary_for(session, run_id))


def list_simulation_runs(bpmn_model_id: str) -> list[dict[str, Any]]:
    with workspace_connection() as session:
        _expire_stale_runs(session)
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
