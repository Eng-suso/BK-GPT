"""Read the existing process authority; write only consultant review actions.

No model call, diagram edit, plan edit, or simulated performance claim occurs
here. The revision binds a proposal to the saved XML and knowledge it inspected.
"""
import hashlib
from datetime import UTC, datetime
from typing import cast

from defusedxml.ElementTree import fromstring
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.process_understanding import ProcessUnderstanding
from backend.schemas.impact_review import (
    CreateImpactReviewAction, ImpactReviewAction, ImpactReviewState, ReviewActionKind,
)
from backend.security import get_current_tenant_id
from backend.workspace_storage import (
    WorkspaceBpmnModel, WorkspaceBpmnReview, WorkspaceImpactReviewAction,
    WorkspaceProcess, workspace_connection,
)


class ReviewNotFound(ValueError):
    pass


class ReviewConflict(ValueError):
    pass


def _state(session: Session, process_id: str, *, lock: bool = False) -> ImpactReviewState:
    tenant = get_current_tenant_id()
    query = select(WorkspaceProcess).where(WorkspaceProcess.id == process_id, WorkspaceProcess.tenant_id == tenant)
    if lock:
        query = query.with_for_update()
    process = session.scalar(query)
    if process is None:
        raise ReviewNotFound("Processo non trovato.")
    model_query = select(WorkspaceBpmnModel).where(WorkspaceBpmnModel.id == process.bpmn_model_id, WorkspaceBpmnModel.tenant_id == tenant)
    review_query = select(WorkspaceBpmnReview).where(WorkspaceBpmnReview.bpmn_model_id == process.bpmn_model_id, WorkspaceBpmnReview.tenant_id == tenant)
    if lock:
        model_query = model_query.with_for_update()
        review_query = review_query.with_for_update()
    model = session.scalar(model_query)
    review = session.scalar(review_query)
    xml = model.xml if model else None
    # Approved plans remain readable. Never reconstruct a plan from canvas names.
    plan_json = review.process_understanding_json if review else "{}"
    plan = ProcessUnderstanding.model_validate_json(plan_json) if plan_json != "{}" else None
    revision = hashlib.sha256(f"{process_id}\0{xml or ''}\0{plan_json}\0{review.version if review else 0}".encode()).hexdigest()
    rows = session.scalars(select(WorkspaceImpactReviewAction).where(
        WorkspaceImpactReviewAction.process_id == process_id,
        WorkspaceImpactReviewAction.tenant_id == tenant,
    ).order_by(WorkspaceImpactReviewAction.created_at.desc(), WorkspaceImpactReviewAction.id)).all()
    return ImpactReviewState(process_id=process_id, base_revision=revision, xml=xml, plan=plan, actions=[_action(row) for row in rows])


def _action(row: WorkspaceImpactReviewAction) -> ImpactReviewAction:
    return ImpactReviewAction(
        id=row.id, node_id=row.node_id, node_name=row.node_name,
        base_revision=row.base_revision, kind=cast(ReviewActionKind, row.kind),
        title=row.title, detail=row.detail, created_at=row.created_at, created_by=row.created_by,
    )


def read_impact_review(process_id: str) -> ImpactReviewState:
    """Read tenant-owned saved process state and the separate review log."""
    with workspace_connection() as session:
        return _state(session, process_id)


def create_impact_review_action(process_id: str, payload: CreateImpactReviewAction, created_by: str) -> ImpactReviewAction:
    """Append an idempotent action; reject foreign, removed or stale targets."""
    with workspace_connection() as session:
        state = _state(session, process_id, lock=True)
        previous = session.get(WorkspaceImpactReviewAction, str(payload.id))
        if previous:
            if (previous.tenant_id != get_current_tenant_id() or previous.process_id != process_id
                or previous.node_id != payload.node_id or previous.base_revision != payload.base_revision
                or previous.kind != payload.kind or previous.title != payload.title or previous.detail != payload.detail
                or previous.created_by != created_by):
                raise ReviewConflict("Identificativo azione già utilizzato.")
            return _action(previous)
        if payload.base_revision != state.base_revision:
            raise ReviewConflict("L'As-Is o il piano è cambiato. Ricarica la review prima di salvare.")
        root = fromstring(state.xml) if state.xml else None
        namespace = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
        task_tags = {namespace + name for name in (
            "task", "userTask", "manualTask", "serviceTask", "sendTask", "receiveTask", "businessRuleTask", "scriptTask",
        )}
        node = next((element for element in root.iter() if element.get("id") == payload.node_id and element.tag in task_tags), None) if root is not None else None
        if node is None:
            raise ValueError("Il task non appartiene all'As-Is salvato.")
        row = WorkspaceImpactReviewAction(
            id=str(payload.id), tenant_id=get_current_tenant_id(), process_id=process_id,
            node_id=payload.node_id, node_name=node.get("name") or payload.node_id,
            base_revision=state.base_revision, kind=payload.kind, title=payload.title,
            detail=payload.detail, created_at=datetime.now(UTC).isoformat(), created_by=created_by,
        )
        session.add(row)
        session.flush()
        result = _action(row)
        session.commit()
        return result
