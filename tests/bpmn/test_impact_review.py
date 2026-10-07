"""Real workspace persistence: hypotheses never mutate the As-Is authority."""
import uuid

import pytest
from sqlalchemy import select

from backend.schemas.impact_review import CreateImpactReviewAction
from backend.security import reset_current_tenant_id, set_current_tenant_id
from backend.settings import settings
from backend.workspace_services.impact_review import (
    ReviewConflict, ReviewNotFound, create_impact_review_action, read_impact_review,
)
from backend.workspace_storage import (
    WorkspaceBpmnModel, WorkspaceBpmnReview, WorkspaceClient, WorkspaceImpactReviewAction,
    WorkspaceProcess, WorkspaceProject, workspace_connection,
)

pytestmark = pytest.mark.skipif(not settings.workspace_database_url, reason="requires an isolated workspace Postgres")
XML = '<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process id="p"><b:userTask id="verify" name="Verificare dati"/><b:endEvent id="end"/></b:process></b:definitions>'


@pytest.fixture()
def process():
    identity = uuid.uuid4().hex
    tenant = f"review-test-{identity}"
    token = set_current_tenant_id(tenant)
    try:
        with workspace_connection() as session:
            client = WorkspaceClient(id=f"c-{identity}", tenant_id=tenant, name="Review test", sector="Test", status="Attivo", owner="Test", contact="")
            project = WorkspaceProject(id=f"p-{identity}", tenant_id=tenant, client=client, name="Review", phase="Discovery", status="In corso", progress=0, process_count=1, next_step="Review", milestones_json="[]", open_issues_json="[]", deliverables_json="[]")
            process = WorkspaceProcess(id=identity, tenant_id=tenant, project=project, bpmn_model_id=f"b-{identity}", name="Process", stage="AS-IS", status="Bozza", owner="Test", readiness=0)
            process.bpmn_model = WorkspaceBpmnModel(id=process.bpmn_model_id, tenant_id=tenant, name="Process", xml=XML)
            session.add(client)
            session.add(WorkspaceBpmnReview(bpmn_model_id=process.bpmn_model_id, tenant_id=tenant, process_id=identity, version=1, source_text="Evidence", process_understanding_json='{"title":"Process","steps":[{"id":"verify","label":"Verificare dati"}]}', bpmn_semantic_model_json="{}", bpmn_brief="Plan", readiness_score=0, missing_information_json="[]", status="approved", created_at="2026-10-07", updated_at="2026-10-07"))
        yield identity
        with workspace_connection() as session:
            session.delete(session.get(WorkspaceBpmnReview, f"b-{identity}"))
            session.delete(session.get(WorkspaceClient, f"c-{identity}"))
    finally:
        reset_current_tenant_id(token)


def payload(process_id: str, **changes) -> CreateImpactReviewAction:
    return CreateImpactReviewAction.model_validate({
        "id": str(uuid.uuid4()), "node_id": "verify", "base_revision": read_impact_review(process_id).base_revision,
        "kind": "candidate", "title": "Validare alla fonte", "detail": "Valutare un controllo di completezza a monte.", **changes,
    })


@pytest.mark.parametrize("kind", ["candidate", "clarification", "deferred"])
def test_actions_persist_separately_and_do_not_change_the_saved_plan_or_xml(process, kind):
    before = read_impact_review(process)
    assert before.plan is not None, "approved plans must remain readable"
    request = payload(process, kind=kind)
    action = create_impact_review_action(process, request, "consultant")
    repeated = create_impact_review_action(process, request, "consultant")
    after = read_impact_review(process)
    assert action == repeated
    assert after.actions == [action]
    assert (after.xml, after.plan, after.base_revision) == (before.xml, before.plan, before.base_revision)


def test_tenant_cannot_read_or_write_another_process(process):
    request = payload(process)
    token = set_current_tenant_id("another-tenant")
    try:
        with pytest.raises(ReviewNotFound):
            read_impact_review(process)
        with pytest.raises(ReviewNotFound):
            create_impact_review_action(process, request, "other")
    finally:
        reset_current_tenant_id(token)


def test_removed_non_task_or_foreign_node_cannot_receive_actions(process):
    for node_id in ("removed", "end", "foreign"):
        with pytest.raises(ValueError, match="task"):
            create_impact_review_action(process, payload(process, node_id=node_id), "consultant")
    assert read_impact_review(process).actions == []


def test_changed_xml_or_plan_rejects_a_stale_proposal(process):
    request = payload(process)
    with workspace_connection() as session:
        model = session.get(WorkspaceBpmnModel, f"b-{process}")
        model.xml = XML.replace("Verificare dati", "Validare dati")
    with pytest.raises(ReviewConflict):
        create_impact_review_action(process, request, "consultant")
    request = payload(process)
    with workspace_connection() as session:
        review = session.get(WorkspaceBpmnReview, f"b-{process}")
        review.version += 1
    with pytest.raises(ReviewConflict):
        create_impact_review_action(process, request, "consultant")


def test_reusing_an_action_id_with_changed_content_is_a_conflict(process):
    request = payload(process)
    create_impact_review_action(process, request, "consultant")
    with pytest.raises(ReviewConflict):
        create_impact_review_action(process, request.model_copy(update={"detail": "Different"}), "consultant")


def test_process_deletion_removes_review_actions(process):
    create_impact_review_action(process, payload(process), "consultant")
    with workspace_connection() as session:
        session.delete(session.get(WorkspaceProcess, process))
    with workspace_connection() as session:
        assert session.scalar(select(WorkspaceImpactReviewAction).where(WorkspaceImpactReviewAction.process_id == process)) is None
