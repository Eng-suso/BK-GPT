"""SIM-14: il workspace degli scenari di un processo, AS-IS piu' alternative.

L'AS-IS tiene la bozza intera del pannello e il seed comune; ogni alternativa
tiene solo la sua patch (``scenario_patch.py``) e si risolve sull'AS-IS di
oggi. Ogni modifica porta la revisione su cui il consulente ha lavorato: se nel
frattempo lo scenario e' cambiato (un'altra scheda, un collega) la modifica si
rifiuta invece di sovrascrivere.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.schemas.simulation_scenarios import (
    BASELINE_LABEL,
    SCENARIO_LABELS,
    WORKSPACE_SEED_MAX,
    CreateScenarioRequest,
    PutScenarioBaselineRequest,
    SimulationScenarioResponse,
    SimulationScenarioWorkspaceResponse,
    UpdateScenarioRequest,
)
from backend.security import get_current_tenant_id
from backend.simulation.scenario_patch import apply_scenario_patch
from backend.workspace_storage import WorkspaceSimulationScenario, workspace_connection


class ScenarioNotFound(LookupError):
    pass


class ScenarioRevisionConflict(Exception):
    """Lo scenario e' cambiato dopo la revisione su cui si e' lavorato."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _rows(session: Session, bpmn_model_id: str, *, lock: bool = False) -> list[WorkspaceSimulationScenario]:
    query = (
        select(WorkspaceSimulationScenario)
        .where(WorkspaceSimulationScenario.tenant_id == get_current_tenant_id())
        .where(WorkspaceSimulationScenario.bpmn_model_id == bpmn_model_id)
        .order_by(WorkspaceSimulationScenario.label)
    )
    if lock:
        query = query.with_for_update()
    return list(session.execute(query).scalars())


def _baseline(rows: list[WorkspaceSimulationScenario]) -> WorkspaceSimulationScenario | None:
    return next((row for row in rows if row.kind == "baseline"), None)


def _to_response(row: WorkspaceSimulationScenario, baseline_draft: dict[str, Any]) -> SimulationScenarioResponse:
    if row.kind == "baseline":
        draft, patch, conflicts = baseline_draft, [], []
    else:
        patch = json.loads(row.patch_json or "[]")
        draft, conflicts = apply_scenario_patch(baseline_draft, patch)
    return SimulationScenarioResponse(
        id=row.id,
        kind="baseline" if row.kind == "baseline" else "alternative",
        label=row.label,
        name=row.name,
        revision=row.revision,
        draft=draft,
        patch=patch,
        conflicts=conflicts,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _workspace(bpmn_model_id: str, rows: list[WorkspaceSimulationScenario]) -> SimulationScenarioWorkspaceResponse:
    baseline = _baseline(rows)
    baseline_draft = json.loads(baseline.draft_json or "{}") if baseline is not None else {}
    return SimulationScenarioWorkspaceResponse(
        bpmn_model_id=bpmn_model_id,
        seed=baseline.seed if baseline is not None else None,
        baseline=_to_response(baseline, baseline_draft) if baseline is not None else None,
        alternatives=[_to_response(row, baseline_draft) for row in rows if row.kind != "baseline"],
    )


def get_scenario_workspace(bpmn_model_id: str) -> SimulationScenarioWorkspaceResponse:
    with workspace_connection() as session:
        return _workspace(bpmn_model_id, _rows(session, bpmn_model_id))


def put_scenario_baseline(bpmn_model_id: str, request: PutScenarioBaselineRequest) -> SimulationScenarioWorkspaceResponse:
    """Crea l'AS-IS (``revision`` assente) o lo aggiorna alla revisione attesa."""
    try:
        with workspace_connection() as session:
            rows = _rows(session, bpmn_model_id, lock=True)
            baseline = _baseline(rows)
            now = _now()
            if baseline is None:
                if request.revision is not None:
                    raise ScenarioRevisionConflict("L'AS-IS non esiste piu': ricarica il workspace.")
                baseline = WorkspaceSimulationScenario(
                    tenant_id=get_current_tenant_id(),
                    bpmn_model_id=bpmn_model_id,
                    kind="baseline",
                    label=BASELINE_LABEL,
                    name=request.name,
                    draft_json=json.dumps(request.draft, ensure_ascii=False),
                    seed=request.seed if request.seed is not None else secrets.randbelow(WORKSPACE_SEED_MAX + 1),
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(baseline)
                rows.append(baseline)
            else:
                if request.revision != baseline.revision:
                    raise ScenarioRevisionConflict("L'AS-IS e' cambiato nel frattempo: ricarica il workspace.")
                baseline.name = request.name
                baseline.draft_json = json.dumps(request.draft, ensure_ascii=False)
                if request.seed is not None:
                    baseline.seed = request.seed
                baseline.revision += 1
                baseline.updated_at = now
            session.flush()
            return _workspace(bpmn_model_id, rows)
    except IntegrityError as exc:
        # Due schede che creano l'AS-IS insieme: la seconda trova quello della prima.
        raise ScenarioRevisionConflict("L'AS-IS e' appena stato creato: ricarica il workspace.") from exc


def create_scenario(bpmn_model_id: str, request: CreateScenarioRequest) -> SimulationScenarioWorkspaceResponse:
    try:
        with workspace_connection() as session:
            rows = _rows(session, bpmn_model_id, lock=True)
            if _baseline(rows) is None:
                raise ValueError("Prima serve l'AS-IS: salva lo scenario attuale.")
            used = {row.label for row in rows}
            label = next((candidate for candidate in SCENARIO_LABELS if candidate not in used), None)
            if label is None:
                raise ValueError(f"Al massimo {len(SCENARIO_LABELS)} scenari oltre l'AS-IS: togline uno prima di aggiungerne un altro.")
            now = _now()
            row = WorkspaceSimulationScenario(
                tenant_id=get_current_tenant_id(),
                bpmn_model_id=bpmn_model_id,
                kind="alternative",
                label=label,
                name=request.name,
                patch_json=json.dumps([op.model_dump(mode="json", exclude_none=True) for op in request.patch], ensure_ascii=False),
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            rows.append(row)
            rows.sort(key=lambda item: item.label)
            return _workspace(bpmn_model_id, rows)
    except IntegrityError as exc:
        raise ScenarioRevisionConflict("Un altro scenario ha appena preso la stessa lettera: riprova.") from exc


def update_scenario(bpmn_model_id: str, scenario_id: int, request: UpdateScenarioRequest) -> SimulationScenarioWorkspaceResponse:
    with workspace_connection() as session:
        rows = _rows(session, bpmn_model_id, lock=True)
        row = next((item for item in rows if item.id == scenario_id and item.kind != "baseline"), None)
        if row is None:
            raise ScenarioNotFound("Scenario non trovato.")
        if request.revision != row.revision:
            raise ScenarioRevisionConflict("Lo scenario e' cambiato nel frattempo: ricarica il workspace.")
        if request.name is not None:
            row.name = request.name
        if request.patch is not None:
            row.patch_json = json.dumps([op.model_dump(mode="json", exclude_none=True) for op in request.patch], ensure_ascii=False)
        row.revision += 1
        row.updated_at = _now()
        session.flush()
        return _workspace(bpmn_model_id, rows)


def delete_scenario(bpmn_model_id: str, scenario_id: int) -> SimulationScenarioWorkspaceResponse:
    """Toglie un'alternativa. L'AS-IS resta: e' il riferimento di tutte le altre."""
    with workspace_connection() as session:
        rows = _rows(session, bpmn_model_id, lock=True)
        row = next((item for item in rows if item.id == scenario_id), None)
        if row is None:
            raise ScenarioNotFound("Scenario non trovato.")
        if row.kind == "baseline":
            raise ValueError("L'AS-IS non si toglie: e' il riferimento degli altri scenari.")
        session.delete(row)
        session.flush()
        return _workspace(bpmn_model_id, [item for item in rows if item.id != scenario_id])


def scenario_revisions(bpmn_model_id: str, scenario_id: int) -> tuple[int, int] | None:
    """(revisione dello scenario, revisione dell'AS-IS), o ``None`` se non e' di questo processo."""
    with workspace_connection() as session:
        rows = _rows(session, bpmn_model_id)
        row = next((item for item in rows if item.id == scenario_id), None)
        baseline = _baseline(rows)
        if row is None or baseline is None:
            return None
        return row.revision, baseline.revision
