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


def review_scope(process_id: str):
    from backend.schemas.chat import CanvasChatScope
    return CanvasChatScope(type="canvas", project_id=f"p-{process_id}", process_id=process_id,
                           bpmn_model_id=f"b-{process_id}", review_node_id="verify",
                           review_base_revision=read_impact_review(process_id).base_revision)


def test_review_chat_resolves_authority_and_rejects_foreign_or_stale_targets(process):
    from fastapi import HTTPException
    from backend.workspace_services.task_review_context import read_task_review_context
    scope = review_scope(process)
    assert read_task_review_context(scope)["name"] == "Verificare dati"
    for changes, status in [({"project_id": "foreign"}, 404), ({"bpmn_model_id": "foreign"}, 404),
                            ({"review_node_id": "end"}, 404), ({"review_base_revision": "a" * 64}, 409)]:
        with pytest.raises(HTTPException) as exc:
            read_task_review_context(scope.model_copy(update=changes))
        assert exc.value.status_code == status
    token = set_current_tenant_id("foreign-tenant")
    try:
        with pytest.raises(HTTPException) as exc:
            read_task_review_context(scope)
        assert exc.value.status_code == 404
    finally:
        reset_current_tenant_id(token)


@pytest.mark.parametrize("target,kind", [("as_is", "as_is_proposal"), ("to_be", "candidate")])
def test_agent_changes_only_a_separate_proposal_and_can_revise_it(process, target, kind):
    from backend.workspace_services.review_proposals import ReviewBpmnOperation, build_review_proposal
    before = read_impact_review(process)
    scope = review_scope(process)
    result = build_review_proposal(scope, target=target, title="Esplicitare verifica", detail="Correzione da discutere.",
                                  operations=[ReviewBpmnOperation(action="update", element_id="verify", name="Verificare completezza")])
    after = read_impact_review(process)
    assert (after.xml, after.plan, after.base_revision) == (before.xml, before.plan, before.base_revision)
    assert after.actions[0].kind == kind
    assert "Verificare completezza" in after.actions[0].proposal_xml
    assert result["saved_separately"] and result["baseline_unchanged"]
    build_review_proposal(scope, target=target, title="Seconda proposta", detail="Ulteriore dettaglio.", base_proposal_id=result["id"],
                          operations=[ReviewBpmnOperation(action="update", element_id="verify", documentation="Richiede dati completi.")])
    latest = read_impact_review(process)
    assert "Verificare completezza" in latest.actions[0].proposal_xml
    assert "Richiede dati completi" in latest.actions[0].proposal_xml
    assert latest.actions[1].proposal_xml == after.actions[0].proposal_xml
    assert latest.xml == before.xml


def test_failed_proposal_operations_are_atomic_and_cannot_use_foreign_bases(process):
    from backend.workspace_services.review_proposals import ReviewBpmnOperation, build_review_proposal
    scope = review_scope(process)
    operations = [ReviewBpmnOperation(action="update", element_id="verify", name="Changed"),
                  ReviewBpmnOperation(action="connect", source_id="verify", target_id="foreign")]
    with pytest.raises(ValueError):
        build_review_proposal(scope, target="as_is", title="Invalid", detail="Invalid proposal.", operations=operations)
    with pytest.raises(ValueError, match="partenza"):
        build_review_proposal(scope, target="as_is", title="Foreign", detail="Foreign base.", operations=operations[:1], base_proposal_id="foreign")
    assert read_impact_review(process).actions == []
    assert read_impact_review(process).xml == XML


def test_review_agent_executes_proposal_tool_with_injected_scope(process, monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from backend.graphs import task_review
    from backend.workspace_services.task_review_context import read_task_review_context

    class ScriptedModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    # Avoid external graph/snapshot projections: this test exercises the real
    # LangGraph tool loop, injected scope and isolated Postgres persistence.
    monkeypatch.setattr(task_review, "load_canvas_context", lambda state: {})
    llm = ScriptedModel(responses=[AIMessage(content="", tool_calls=[{
        "name": "create_review_bpmn_proposal", "id": "proposal-call", "type": "tool_call",
        "args": {"target": "as_is", "title": "Precisare controllo", "detail": "Proposta da presentare.",
                 "operations": [{"action": "update", "element_id": "verify", "name": "Verificare completezza"}]},
    }]), AIMessage(content="Ho preparato una proposta separata.")])
    scope = review_scope(process)
    state = {"messages": [HumanMessage(content="Rinomina il task nella proposta As-Is.")],
             "project_id": scope.project_id, "process_id": process, "bpmn_model_id": scope.bpmn_model_id,
             "review_task_context": read_task_review_context(scope)}
    result = task_review.build_task_review_subgraph(llm, lambda current: current["messages"]).invoke(state)
    assert result["messages"][-1].content == "Ho preparato una proposta separata."
    review = read_impact_review(process)
    assert len(review.actions) == 1
    assert "Verificare completezza" in review.actions[0].proposal_xml
    assert review.xml == XML
