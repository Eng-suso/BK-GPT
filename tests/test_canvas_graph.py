from backend.graphs.canvas_edit.graph import (
    canvas_completion_report,
    evaluate_canvas_completion,
    parse_canvas_router_json,
    route_after_canvas_layout,
    route_after_canvas_completion_check,
    route_after_canvas_work,
    route_after_validation_subgraph,
)
from backend.graphs.canvas_edit.subgraphs.layout.graph import run_canvas_drawing_agent
import backend.graphs.canvas_edit.subgraphs.layout.graph as layout_graph_module
from backend.graphs.canvas_edit.skills_manifest import required_skills_for
from backend.graphs.canvas_edit.tools import (
    canvas_macro_tools,
    construction_tools,
    patch_edit_tools,
    validation_tools,
)
from backend.graphs.routing_contracts import CAPABILITY_REGISTRY
from backend.bpmn_semantic import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessActor,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
)
from backend.services.agent_runtime import STREAMABLE_AGENT_NODES
from backend.toolsets.bpmn import bpmn_review_tools, manage_canvas_bpmn_model
from backend.workspace_services.bpmn_canvas_edit import (
    clear_bpmn_process,
    delete_bpmn_element,
    layout_bpmn_di,
    list_bpmn_elements,
    optimize_bpmn_layout,
    validate_bpmn_layout,
    validate_bpmn_xml,
)
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process
from backend.workspace_services.canvas_business_report import canvas_business_report


def tool_names(tools: list) -> set[str]:
    return {tool.name for tool in tools}


def test_parse_canvas_router_json_returns_structured_state():
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.91,
          "needs_clarification": false,
          "clarification_question": null,
          "entity_hints": {"canvas": "proc-bpmn", "element": "Task_Validate"},
          "canvas_mode": "patch_edit",
          "canvas_objective": "rename one validation task",
          "expected_result": "local task rename",
          "reason": "The request only changes one element label"
        }
        """,
        user_request="rinomina la task validazione",
        state={
            "bpmn_model_id": "proc-bpmn",
            "effective_bpmn_xml": "<definitions />",
        },
    )

    assert result["canvas_route"] == "patch_edit"
    assert result["canvas_mode"] == "patch_edit"
    assert result["delegation_target"] == "patch_edit_subgraph"
    assert result["routing_confidence"] == 0.91
    assert result["entity_hints"] == {"canvas": "proc-bpmn", "element": "Task_Validate"}
    assert result["delegation_events"][0]["target"] == "patch_edit_subgraph"


def test_parse_canvas_router_json_blocks_invalid_route():
    result = parse_canvas_router_json('{"route":"unknown","confidence":5}')

    assert result["canvas_route"] == "clarification"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 0.0
    assert result["needs_clarification"] is True
    assert result["orchestration_status"] == "invalid_structured_decision"


def test_canvas_router_refuses_unregistered_capability():
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.8,
          "suggested_capability": "canvas.run_arbitrary_tool",
          "reason": "Bad capability."
        }
        """,
        state={
            "bpmn_model_id": "proc-bpmn",
            "effective_bpmn_xml": "<definitions />",
        },
    )

    assert result["canvas_route"] == "clarification"
    assert result["delegation_events"] == []
    assert result["orchestration_status"] == "unregistered_capability"


def test_canvas_patch_requires_current_canvas_xml():
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.86,
          "goal": "PATCH_CANVAS",
          "intent": "local_canvas_patch",
          "next_action": "PATCH_EXISTING_XML",
          "suggested_capability": "canvas.patch_edit",
          "canvas_mode": "patch_edit",
          "workflow_scope": "local_operation",
          "reason": "Rename one element."
        }
        """,
        state={"bpmn_model_id": "proc-bpmn"},
    )

    assert result["canvas_route"] == "clarification"
    assert result["delegation_target"] is None
    assert result["orchestration_status"] == "missing_prerequisite"
    assert "Missing prerequisite: effective_bpmn_xml" in result["blocking_conditions"]


def test_canvas_construction_allows_raw_process_description_without_semantic_context():
    result = parse_canvas_router_json(
        """
        {
          "route": "construction",
          "confidence": 0.88,
          "goal": "MAP_PROCESS_TO_BPMN",
          "intent": "map_raw_process_description",
          "next_action": "PREPARE_BPMN_REVIEW",
          "suggested_capability": "canvas.construction",
          "canvas_mode": "construction",
          "workflow_scope": "full_workflow",
          "reason": "The user supplied a substantive process description to map."
        }
        """,
        user_request="L'Ufficio Acquisti aggiorna il database fornitori...",
        state={"bpmn_model_id": "proc-bpmn"},
    )

    assert result["canvas_route"] == "construction"
    assert result["delegation_target"] == "construction_subgraph"
    assert result["authorized_capability"] == "canvas.construction"
    assert result["orchestration_status"] == "authorized"


def test_canvas_completion_loop_marks_valid_canvas_completed(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""
    monkeypatch.setattr(
        "backend.graphs.canvas_edit.graph.workspace_database.get_bpmn_model",
        lambda bpmn_model_id: {"id": bpmn_model_id, "xml": xml},
    )

    result = evaluate_canvas_completion(
        {
            "bpmn_model_id": "proc-bpmn",
            "canvas_loop_attempt": 0,
            "canvas_loop_max_attempts": 2,
            "canvas_objective": "Rinomina un passaggio",
        }
    )

    assert result["canvas_loop_status"] == "completed"
    assert result["validation_report"]["issues"] == []
    assert route_after_canvas_completion_check(result) == "completion_report"


def test_canvas_completion_loop_retries_patch_for_blocking_validation_issue(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""
    process_understanding = {
        "schema_version": "process_understanding.v1",
        "language": "it",
        "title": "Order Review",
        "steps": [{"id": "Task_Review", "label": "Rivedi ordine", "type": "user_task"}],
        "sequence": ["Task_Review"],
        "decisions": [{"id": "Gateway_Check", "label": "Ordine approvato?", "outcomes": ["Si", "No"]}],
        "unknowns": [],
    }
    canonical_semantic_model = build_bpmn_semantic_model(
        process_id="Process_Test",
        process_name="Order Review",
        process=ProcessUnderstanding.model_validate(process_understanding)
    ).model_dump(mode="json")
    monkeypatch.setattr(
        "backend.graphs.canvas_edit.graph.workspace_database.get_bpmn_model",
        lambda bpmn_model_id: {"id": bpmn_model_id, "xml": xml},
    )

    result = evaluate_canvas_completion(
        {
            "bpmn_model_id": "proc-bpmn",
            "bpmn_semantic_model": canonical_semantic_model,
            "canvas_loop_attempt": 0,
            "canvas_loop_max_attempts": 2,
        }
    )

    assert result["canvas_loop_status"] == "needs_fix"
    assert result["canvas_route"] == "patch_edit"
    assert route_after_canvas_completion_check(result) == "patch_edit_subgraph"
    assert "Il processo contiene decisioni ma il canvas non contiene gateway." in result["validation_report"]["issues"]


def test_canvas_completion_treats_intentional_clear_as_completed(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test" />
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""
    process_understanding = {
        "schema_version": "process_understanding.v1",
        "language": "it",
        "title": "Order Review",
        "steps": [{"id": "Task_Review", "label": "Rivedi ordine", "type": "user_task"}],
        "sequence": ["Task_Review"],
        "decisions": [{"id": "Gateway_Check", "label": "Ordine approvato?", "outcomes": ["Si", "No"]}],
        "unknowns": [],
    }
    canonical_semantic_model = build_bpmn_semantic_model(
        process_id="Process_Test",
        process_name="Order Review",
        process=ProcessUnderstanding.model_validate(process_understanding),
    ).model_dump(mode="json")
    monkeypatch.setattr(
        "backend.graphs.canvas_edit.graph.workspace_database.get_bpmn_model",
        lambda bpmn_model_id: {"id": bpmn_model_id, "xml": xml},
    )

    result = evaluate_canvas_completion(
        {
            "bpmn_model_id": "proc-bpmn",
            "bpmn_semantic_model": canonical_semantic_model,
            "canvas_objective": "elimina quello che c'e nel canvas",
            "intent": "clear_canvas",
            "canvas_loop_attempt": 0,
            "canvas_loop_max_attempts": 2,
        }
    )

    assert result["canvas_loop_status"] == "completed"
    assert result["validation_report"]["completion_kind"] == "empty_canvas"
    assert result["validation_report"]["issues"] == []
    assert result["validation_report"]["semantic_valid"] is None
    assert route_after_canvas_completion_check(result) == "completion_report"
    final_report = canvas_completion_report(result)
    content = final_report["messages"][0].content
    assert content == "Canvas svuotato. Ho verificato che non ci siano piu' elementi o collegamenti visibili."
    assert "Payload semantico" not in content
    assert "gateway" not in content.casefold()


def test_clear_canvas_intent_skips_semantic_validation_subgraph():
    state = {
        "canvas_route": "patch_edit",
        "canvas_loop_status": "running",
        "canvas_objective": "elimina quello che c'e nel canvas",
    }

    assert route_after_canvas_work(state) == "evaluate_canvas_completion"
    assert route_after_canvas_layout({**state, "canvas_layout_status": "completed"}) == "evaluate_canvas_completion"


def test_canvas_subagent_intermediate_messages_are_not_streamed():
    assert "canvas_completion_report" in STREAMABLE_AGENT_NODES
    assert "canvas_patch_edit_agent" not in STREAMABLE_AGENT_NODES
    assert "canvas_construction_agent" not in STREAMABLE_AGENT_NODES
    assert "canvas_validation_agent" not in STREAMABLE_AGENT_NODES


def test_standalone_canvas_validation_does_not_enter_completion_loop():
    assert route_after_validation_subgraph({"canvas_loop_status": None}) == "end"


def test_canvas_capability_registry_declares_canvas_owners():
    assert CAPABILITY_REGISTRY["canvas.patch_edit"].target == "patch_edit_subgraph"
    assert CAPABILITY_REGISTRY["canvas.construction"].target == "construction_subgraph"
    assert CAPABILITY_REGISTRY["canvas.layout"].target == "layout_subgraph"
    assert CAPABILITY_REGISTRY["canvas.validation"].target == "validation_subgraph"


def test_canvas_toolsets_are_owned_and_facade_first():
    macro_names = tool_names(canvas_macro_tools)
    patch_names = tool_names(patch_edit_tools)
    construction_names = tool_names(construction_tools)
    validation_names = tool_names(validation_tools)

    assert "manage_canvas_bpmn_model" in macro_names
    assert "prepare_canvas_delegation_payload" in macro_names
    assert "retrieve_process_canvas_traceability_context" in macro_names
    assert patch_names == {
        "manage_canvas_bpmn_model",
        "get_process_semantic_context",
        "retrieve_process_canvas_traceability_context",
        "search_bpmn_preferences",
        "remember_bpmn_preference",
    }
    assert "prepare_canvas_bpmn_review" in construction_names
    assert "approve_canvas_bpmn_review" in construction_names
    assert "retrieve_process_canvas_traceability_context" in construction_names
    assert "manage_canvas_construction" in construction_names
    assert "manage_canvas_bpmn_model" in validation_names
    assert "manage_canvas_validation" in validation_names
    assert "get_process_semantic_context" in validation_names


def test_canvas_skills_manifest_declares_required_skills():
    assert "canvas_macro_orchestration" in required_skills_for("canvas_macro")
    assert "canvas_patch_edit" in required_skills_for("patch_edit_subgraph")
    assert "canvas_construction" in required_skills_for("construction_subgraph")
    assert "canvas_layout" in required_skills_for("layout_subgraph")
    assert "canvas_validation" in required_skills_for("validation_subgraph")


def test_bpmn_review_tools_include_canvas_facade_for_compatibility():
    assert "manage_canvas_bpmn_model" in tool_names(bpmn_review_tools)
    assert "manage_canvas_construction" in tool_names(bpmn_review_tools)
    assert "manage_canvas_validation" in tool_names(bpmn_review_tools)
    assert manage_canvas_bpmn_model.name == "manage_canvas_bpmn_model"


def _process_with_exception() -> ProcessUnderstanding:
    """Build a process model with a timeout exception attached to its waiting step.
    
    Returns:
        ProcessUnderstanding: A two-step operations process with a 15-day timeout exception.
    """
    return ProcessUnderstanding(
        title="Con eccezione",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_Wait", label="Attendi esito", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Close", label="Chiudi", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Wait", "Task_Close"],
        sequence=["Task_Wait", "Task_Close"],
        exceptions=[
            ProcessExceptionPath(
                id="Exc_TO",
                label="Scaduto il termine",
                trigger="timeout 15 giorni",
                handling="Sollecita",
                attached_to_step_id="Task_Wait",
            )
        ],
    )


def test_boundary_event_survives_layout_and_is_listed_and_positioned():
    model = build_bpmn_semantic_model(
        process_id="Process_Exc", process_name="Con eccezione", process=_process_with_exception()
    )
    xml = semantic_model_to_bpmn_xml(model)
    boundary_id = next(n.id for n in model.flowNodes if n.type == "boundaryEvent")

    relaid = layout_bpmn_di(xml)
    assert f'bpmnElement="{boundary_id}"' in relaid
    assert validate_bpmn_layout(relaid)["valid"] is True
    assert validate_bpmn_xml(relaid)["valid"] is True
    assert any(e["id"] == boundary_id for e in list_bpmn_elements(relaid))


def test_deleting_host_activity_cascades_its_boundary_event():
    model = build_bpmn_semantic_model(
        process_id="Process_Exc", process_name="Con eccezione", process=_process_with_exception()
    )
    xml = semantic_model_to_bpmn_xml(model)
    wait_id = next(n.id for n in model.flowNodes if n.name == "Attendi esito")
    boundary_id = next(n.id for n in model.flowNodes if n.type == "boundaryEvent")

    updated, report = delete_bpmn_element(xml, wait_id)
    ids = {e["id"] for e in list_bpmn_elements(updated)}
    assert wait_id not in ids
    assert boundary_id not in ids
    assert boundary_id in report["removed_boundary_events"]
    assert f'attachedToRef="{wait_id}"' not in updated
    assert validate_bpmn_xml(updated)["valid"] is True


def test_clear_bpmn_process_removes_visible_canvas_elements():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Input"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Collect" name="Raccolta dati"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="Output"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Collect" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Collect" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""

    updated_xml, change = clear_bpmn_process(xml)

    assert change["removed_count"] == 5
    assert {item["name"] for item in change["removed"]} >= {"Input", "Raccolta dati", "Output"}
    assert list_bpmn_elements(updated_xml) == [
        {"id": "Process_Test", "type": "process", "name": "", "documentation": ""}
    ]
    validation = validate_bpmn_xml(updated_xml)
    assert validation["valid"] is True
    assert validation["counts"] == {"flow_nodes": 0, "sequence_flows": 0}


def test_canvas_drawing_agent_removes_semantic_visual_artifacts_before_layout(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
    <bpmn:dataObjectReference id="Data_Order" name="Ordine" />
    <bpmn:textAnnotation id="TextAnnotation_1"><bpmn:text>Regola business visiva</bpmn:text></bpmn:textAnnotation>
    <bpmn:association id="Association_1" sourceRef="Task_Review" targetRef="TextAnnotation_1" />
  </bpmn:process>
</bpmn:definitions>"""
    saved = {}

    monkeypatch.setattr(
        layout_graph_module.workspace_database,
        "get_bpmn_model",
        lambda bpmn_model_id: {"id": bpmn_model_id, "process_id": "proc-1", "xml": xml},
    )

    def fake_update_bpmn_model(bpmn_model_id, updated_xml, change_summary, source):
        saved["xml"] = updated_xml
        saved["source"] = source
        return {"id": bpmn_model_id, "process_id": "proc-1", "xml": updated_xml}

    monkeypatch.setattr(layout_graph_module.workspace_database, "update_bpmn_model", fake_update_bpmn_model)

    result = run_canvas_drawing_agent({"bpmn_model_id": "proc-bpmn"})

    assert result["canvas_layout_status"] == "completed"
    assert saved["source"] == "canvas_layout_agent"
    assert "<bpmn:textAnnotation" not in saved["xml"]
    assert "<bpmn:association" not in saved["xml"]
    assert "<bpmn:dataObjectReference" not in saved["xml"]
    assert validate_bpmn_xml(saved["xml"])["valid"] is True


def test_layout_bpmn_di_wraps_long_process_into_readable_rows():
    tasks = "\n".join(
        f'    <bpmn:userTask id="Task_{idx}" name="Attivita molto lunga numero {idx}">'
        f'<bpmn:incoming>Flow_{idx}</bpmn:incoming><bpmn:outgoing>Flow_{idx + 1}</bpmn:outgoing></bpmn:userTask>'
        for idx in range(1, 13)
    )
    flows = "\n".join(
        f'    <bpmn:sequenceFlow id="Flow_{idx}" sourceRef="{source}" targetRef="{target}" />'
        for idx, (source, target) in enumerate(
            [("Start", "Task_1")]
            + [(f"Task_{idx}", f"Task_{idx + 1}") for idx in range(1, 12)]
            + [("Task_12", "End")],
            start=1,
        )
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
{tasks}
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_13</bpmn:incoming></bpmn:endEvent>
{flows}
  </bpmn:process>
</bpmn:definitions>"""

    updated_xml = layout_bpmn_di(xml)
    result = validate_bpmn_layout(updated_xml)
    bounds = result["metrics"]["bounds"]

    assert result["valid"] is True
    assert bounds["width"] <= 1900
    assert bounds["height"] > 400


def test_optimize_bpmn_layout_retries_until_canvas_is_readable():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_1" name="Raccogli dati"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="Task_2" name="Verifica dati"><bpmn:incoming>Flow_2</bpmn:incoming><bpmn:outgoing>Flow_3</bpmn:outgoing></bpmn:userTask>
    <bpmn:userTask id="Task_3" name="Registra esito"><bpmn:incoming>Flow_3</bpmn:incoming><bpmn:outgoing>Flow_4</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_4</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Task_2" />
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Task_2" targetRef="Task_3" />
    <bpmn:sequenceFlow id="Flow_4" sourceRef="Task_3" targetRef="End" />
  </bpmn:process>
</bpmn:definitions>"""

    updated_xml, optimization = optimize_bpmn_layout(xml)
    report = validate_bpmn_layout(updated_xml)

    assert len(optimization["attempts"]) > 1
    assert optimization["attempts"][0]["report"]["warnings"]
    assert optimization["valid"] is True
    assert report["valid"] is True
    assert not report["warnings"]


def test_semantic_canvas_validation_flags_missing_gateway_for_decision():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""
    process_understanding = {
        "schema_version": "process_understanding.v1",
        "language": "it",
        "title": "Order Review",
        "steps": [{"id": "Task_Review", "label": "Rivedi ordine", "type": "user_task"}],
        "sequence": ["Task_Review"],
        "decisions": [{"id": "Gateway_Check", "label": "Ordine approvato?", "outcomes": ["Si", "No"]}],
        "unknowns": [],
    }

    result = validate_canvas_against_process(
        xml=xml,
        process_understanding=process_understanding,
        bpmn_semantic_model=None,
    )

    assert result["valid"] is False
    assert "Il processo contiene decisioni ma il canvas non contiene gateway." in result["issues"]


def test_canvas_business_report_hides_developer_language():
    report = canvas_business_report(
        {
            "issues": [
                "Gateway Gateway_Check ha meno di due uscite.",
                "Sequence flow Flow_1 ha sourceRef non valido: Missing_Node",
            ],
            "warnings": [
                "BPMNSemanticModel non disponibile: validazione semantica limitata.",
                "XML BPMN non valido.",
            ],
            "counts": {
                "flow_nodes": 3,
                "sequence_flows": 2,
                "gateways": 1,
                "lanes": 0,
                "data_objects": 0,
                "annotations": 0,
            },
            "coverage": {},
        }
    )
    rendered = str(report)
    normalized = rendered.casefold()

    assert "punto di decisione" in normalized
    assert "collegamento" in normalized
    assert "struttura del processo" in normalized
    assert "gateway" not in normalized
    assert "sequenceflow" not in normalized
    assert "sourceref" not in normalized
    assert "bpmnsemanticmodel" not in normalized
    assert "xml" not in normalized
    assert "gateway_check" not in normalized
    assert "missing_node" not in normalized
