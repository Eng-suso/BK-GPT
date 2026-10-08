"""Real workspace persistence: hypotheses never mutate the As-Is authority."""
import uuid

from backend.workspace_services.bpmn_canvas_edit import layout_bpmn_di

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
XML = layout_bpmn_di('<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process id="p"><b:startEvent id="start"/><b:userTask id="verify" name="Verificare dati"><b:documentation>DeliR traceability: {"source_refs":["steps:verify"]}</b:documentation></b:userTask><b:endEvent id="end"/><b:sequenceFlow id="begin" sourceRef="start" targetRef="verify"/><b:sequenceFlow id="finish" sourceRef="verify" targetRef="end"/></b:process></b:definitions>')


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


def test_agent_draws_a_new_task_owner_and_reconnected_flows_on_a_proposal(process, monkeypatch):
    import json
    import os
    from pathlib import Path
    from defusedxml.ElementTree import fromstring
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from backend.graphs import task_review
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_layout
    from backend.workspace_services.task_review_context import read_task_review_context

    class ScriptedModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    operations = [
        {"action": "add", "element_type": "lane", "element_id": "buying", "name": "Acquisti"},
        {"action": "assign_lane", "element_id": "verify", "lane_id": "buying"},
        {"action": "add", "element_type": "userTask", "element_id": "record", "name": "Registrare esito verifica"},
        {"action": "assign_lane", "element_id": "record", "lane_id": "buying"},
        {"action": "reconnect", "element_id": "finish", "source_id": "record"},
        {"action": "connect", "element_id": "handoff", "source_id": "verify", "target_id": "record"},
    ]
    monkeypatch.setattr(task_review, "load_canvas_context", lambda state: {})
    llm = ScriptedModel(responses=[AIMessage(content="", tool_calls=[{
        "name": "create_review_bpmn_proposal", "id": "structural-proposal", "type": "tool_call",
        "args": {"target": "as_is", "title": "Documentare l’esito", "detail": "Nuova attività nella proposta As-Is.", "operations": operations},
    }]), AIMessage(content="Proposta disegnata separatamente.")])
    scope = review_scope(process)
    initial = read_impact_review(process)
    result = task_review.build_task_review_subgraph(llm, lambda current: current["messages"]).invoke({
        "messages": [HumanMessage(content="Nella proposta aggiungi un task per registrare l’esito dopo la verifica, con owner Acquisti.")],
        "project_id": scope.project_id, "process_id": process, "bpmn_model_id": scope.bpmn_model_id,
        "review_task_context": read_task_review_context(scope),
    })
    tool_result = json.loads(next(message.content for message in result["messages"] if message.type == "tool"))
    assert tool_result["validation"]["layout"]["valid"]
    review = read_impact_review(process)
    assert len(review.actions) == 1
    proposal = review.actions[0].proposal_xml
    assert validate_bpmn_layout(proposal)["valid"]
    root = fromstring(proposal)
    ns = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
    lane = root.find(f".//{ns}lane[@id='buying']")
    assert {ref.text for ref in lane.findall(ns + "flowNodeRef")} == {"verify", "record"}
    flows = {(e.get("sourceRef"), e.get("targetRef")) for e in root.iter(ns + "sequenceFlow")}
    assert flows == {("start", "verify"), ("verify", "record"), ("record", "end")}
    assert (review.xml, review.plan, review.base_revision) == (initial.xml, initial.plan, initial.base_revision)
    assert "steps:verify" in proposal
    from xml.etree.ElementTree import canonicalize

    artifacts = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "review-agent"
    # Optional bridge to browser validation: the XML is produced by the real
    # agent tool and editing engine here, not fabricated in the Playwright route.
    if output := os.environ.get("BKGPT_REVIEW_ARTIFACT"):
        Path(output).write_text(proposal, encoding="utf-8")
        Path(output).with_suffix(".baseline.bpmn").write_text(initial.xml, encoding="utf-8")
    assert canonicalize(proposal) == canonicalize((artifacts / "proposal.bpmn").read_text(encoding="utf-8"))
    assert canonicalize(initial.xml) == canonicalize((artifacts / "baseline.bpmn").read_text(encoding="utf-8"))



def _translated_di(xml):
    """A legitimate consultant layout change, including connector waypoints."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for element in root.iter():
        if element.tag.endswith(("}Bounds", "}waypoint")):
            element.set("x", str(float(element.get("x")) + 23))
            element.set("y", str(float(element.get("y")) + 17))
    return ET.tostring(root, encoding="unicode")


def test_manual_di_is_preserved_but_runtime_agent_cannot_choose_geometry(process):
    from backend import workspace_database as db
    from backend.agents.chat_mode import bind_active_mode
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_layout

    model_id = f"b-{process}"
    translated = _translated_di(XML)
    assert validate_bpmn_layout(translated)["valid"]
    human = db.update_bpmn_model(model_id, translated)
    assert human["xml"] == translated
    assert db.list_bpmn_versions(model_id)[0]["xml"] == translated
    # Even a future agent using the default manual source cannot bypass policy.
    with bind_active_mode("agent"):
        agent = db.update_bpmn_model(model_id, translated)
    expected = apply_enterprise_layout(translated, process_name="Process")
    assert agent["xml"] == expected and agent["xml"] != translated
    assert db.list_bpmn_versions(model_id)[0]["xml"] == expected


def test_manual_invalid_geometry_is_rejected_atomically(process):
    from backend import workspace_database as db
    import xml.etree.ElementTree as ET

    model_id = f"b-{process}"
    before = db.get_bpmn_model(model_id)
    versions = db.list_bpmn_versions(model_id)
    root = ET.fromstring(XML)
    bounds = root.find(".//{http://www.omg.org/spec/DD/20100524/DC}Bounds")
    bounds.set("width", "nan")
    with pytest.raises(ValueError, match="non valido"):
        db.update_bpmn_model(model_id, ET.tostring(root, encoding="unicode"))
    assert db.get_bpmn_model(model_id)["xml"] == before["xml"]
    assert db.list_bpmn_versions(model_id) == versions


def test_agent_restore_uses_policy_and_human_restore_keeps_saved_manual_di(process):
    from backend import workspace_database as db
    from backend.agents.chat_mode import bind_active_mode
    from backend.bpmn.canvas_layout import apply_enterprise_layout

    model_id = f"b-{process}"
    translated = _translated_di(XML)
    saved = db.update_bpmn_model(model_id, translated)
    with bind_active_mode("agent"):
        restored = db.restore_bpmn_version(model_id, saved["version_id"])
    assert restored["bpmn_model"]["xml"] == apply_enterprise_layout(translated, process_name="Process")
    restored = db.restore_bpmn_version(model_id, saved["version_id"])
    assert restored["bpmn_model"]["xml"] == translated


def test_manual_semantic_owner_refs_are_validated_without_relayout(process):
    from backend import workspace_database as db
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    model_id = f"b-{process}"
    owned = XML.replace('<bpmn:process id="p">', '<bpmn:process id="p"><bpmn:laneSet id="roles"><bpmn:lane id="buyer" name="Acquisti"><bpmn:flowNodeRef>verify</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>')
    owned = apply_enterprise_layout(owned)
    saved = db.update_bpmn_model(model_id, _translated_di(owned))
    assert saved["xml"] == _translated_di(owned)
    invalid = owned.replace('<bpmn:flowNodeRef>verify</bpmn:flowNodeRef>', '<bpmn:flowNodeRef>missing</bpmn:flowNodeRef>')
    with pytest.raises(ValueError, match="riferimenti non validi"):
        db.update_bpmn_model(model_id, invalid)
    assert db.get_bpmn_model(model_id)["xml"] == saved["xml"]


def test_missing_manual_connector_coordinate_returns_validation_error(process):
    from backend import workspace_database as db
    import xml.etree.ElementTree as ET
    root = ET.fromstring(XML)
    point = root.find(".//{http://www.omg.org/spec/DD/20100524/DI}waypoint")
    del point.attrib["x"]
    with pytest.raises(ValueError, match="non valido"):
        db.update_bpmn_model(f"b-{process}", ET.tostring(root, encoding="unicode"))
    assert db.get_bpmn_model(f"b-{process}")["xml"] == XML


def test_manual_expanded_subprocess_is_preserved_and_agent_policy_collapses_only_its_di(process):
    from backend import workspace_database as db
    from backend.agents.chat_mode import bind_active_mode
    import xml.etree.ElementTree as ET
    b = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
    bd = "{http://www.omg.org/spec/BPMN/20100524/DI}"
    dc = "{http://www.omg.org/spec/DD/20100524/DC}"
    root = ET.fromstring(XML)
    host = root.find(f".//{b}userTask[@id='verify']")
    host.tag = b + "subProcess"
    ET.SubElement(host, b + "startEvent", {"id": "internalStart"})
    ET.SubElement(host, b + "userTask", {"id": "internal"})
    ET.SubElement(host, b + "sequenceFlow", {"id": "internalFlow", "sourceRef": "internalStart", "targetRef": "internal"})
    host_shape = root.find(f".//{bd}BPMNShape[@bpmnElement='verify']")
    host_shape.set("isExpanded", "true")
    bounds = host_shape.find(dc + "Bounds")
    shape = ET.SubElement(root.find(f".//{bd}BPMNPlane"), bd + "BPMNShape", {"id": "internal_di", "bpmnElement": "internal"})
    ET.SubElement(shape, dc + "Bounds", {"x": str(float(bounds.get("x")) + 20), "y": str(float(bounds.get("y")) + 20), "width": "100", "height": "40"})
    inner_bounds = shape.find(dc + "Bounds")
    inner_bounds.set("x", str(float(bounds.get("x")) + 68))
    inner_bounds.set("y", str(float(bounds.get("y")) + 22))
    inner_bounds.set("width", "60")
    inner_bounds.set("height", "36")
    start_shape = ET.SubElement(root.find(f".//{bd}BPMNPlane"), bd + "BPMNShape", {"id": "internalStart_di", "bpmnElement": "internalStart"})
    ET.SubElement(start_shape, dc + "Bounds", {"x": str(float(bounds.get("x")) + 20), "y": str(float(bounds.get("y")) + 22), "width": "36", "height": "36"})
    edge = ET.SubElement(root.find(f".//{bd}BPMNPlane"), bd + "BPMNEdge", {"id": "internalFlow_di", "bpmnElement": "internalFlow"})
    for offset in (56, 68):
        ET.SubElement(edge, "{http://www.omg.org/spec/DD/20100524/DI}waypoint", {"x": str(float(bounds.get("x")) + offset), "y": str(float(bounds.get("y")) + 40)})
    xml = ET.tostring(root, encoding="unicode")
    model_id = f"b-{process}"
    assert db.update_bpmn_model(model_id, xml)["xml"] == xml
    with bind_active_mode("agent"):
        actual = db.update_bpmn_model(model_id, xml)["xml"]
    regenerated = ET.fromstring(actual)
    assert regenerated.find(f".//{b}userTask[@id='internal']") is not None
    assert regenerated.find(f".//{bd}BPMNShape[@bpmnElement='internal']") is None
    assert regenerated.find(f".//{bd}BPMNShape[@bpmnElement='verify']").get("isExpanded") == "false"
