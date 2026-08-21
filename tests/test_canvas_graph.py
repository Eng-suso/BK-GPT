from backend.graphs.canvas_edit.graph import parse_canvas_router_json
from backend.graphs.canvas_edit.skills_manifest import required_skills_for
from backend.graphs.canvas_edit.tools import (
    canvas_macro_tools,
    construction_tools,
    patch_edit_tools,
    validation_tools,
)
from backend.toolsets.bpmn import bpmn_review_tools, manage_canvas_bpmn_model


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
    assert "manage_canvas_bpmn_model" in validation_names
    assert "get_process_semantic_context" in validation_names


def test_canvas_skills_manifest_declares_required_skills():
    assert "canvas_macro_orchestration" in required_skills_for("canvas_macro")
    assert "canvas_patch_edit" in required_skills_for("patch_edit_subgraph")
    assert "canvas_construction" in required_skills_for("construction_subgraph")
    assert "canvas_validation" in required_skills_for("validation_subgraph")


def test_bpmn_review_tools_include_canvas_facade_for_compatibility():
    assert "manage_canvas_bpmn_model" in tool_names(bpmn_review_tools)
    assert manage_canvas_bpmn_model.name == "manage_canvas_bpmn_model"
