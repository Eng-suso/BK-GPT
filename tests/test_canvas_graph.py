from backend.graphs.canvas_edit.graph import parse_canvas_router_json
from backend.graphs.canvas_edit.skills_manifest import required_skills_for
from backend.graphs.canvas_edit.tools import (
    canvas_macro_tools,
    construction_tools,
    patch_edit_tools,
    validation_tools,
)
from backend.toolsets.bpmn import bpmn_review_tools, manage_canvas_bpmn_model
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process


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
    )

    assert result["canvas_route"] == "patch_edit"
    assert result["canvas_mode"] == "patch_edit"
    assert result["delegation_target"] == "patch_edit_subgraph"
    assert result["routing_confidence"] == 0.91
    assert result["entity_hints"] == {"canvas": "proc-bpmn", "element": "Task_Validate"}
    assert result["delegation_events"][0]["target"] == "patch_edit_subgraph"


def test_parse_canvas_router_json_falls_back_to_direct_for_invalid_route():
    result = parse_canvas_router_json('{"route":"unknown","confidence":5}')

    assert result["canvas_route"] == "direct"
    assert result["delegation_target"] is None
    assert result["routing_confidence"] == 1.0


def test_canvas_toolsets_are_owned_and_facade_first():
    macro_names = tool_names(canvas_macro_tools)
    patch_names = tool_names(patch_edit_tools)
    construction_names = tool_names(construction_tools)
    validation_names = tool_names(validation_tools)

    assert "manage_canvas_bpmn_model" in macro_names
    assert "prepare_canvas_delegation_payload" in macro_names
    assert patch_names == {
        "manage_canvas_bpmn_model",
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
    assert "canvas_validation" in required_skills_for("validation_subgraph")


def test_bpmn_review_tools_include_canvas_facade_for_compatibility():
    assert "manage_canvas_bpmn_model" in tool_names(bpmn_review_tools)
    assert "manage_canvas_construction" in tool_names(bpmn_review_tools)
    assert "manage_canvas_validation" in tool_names(bpmn_review_tools)
    assert manage_canvas_bpmn_model.name == "manage_canvas_bpmn_model"


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
