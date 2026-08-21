from typing import Literal

from backend.toolsets.bpmn import (
    approve_canvas_bpmn_review,
    manage_canvas_bpmn_model,
    prepare_canvas_bpmn_review,
)
from backend.toolsets.memory import remember_bpmn_preference, search_bpmn_preferences
from backend.toolsets.process_memory import retrieve_process_canvas_traceability_context
from backend.graphs.process.tools import get_process_semantic_context
from backend.toolsets.workspace import (
    enterprise_tool_result,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_workspace_process,
)
from langchain_core.tools import tool
from pydantic import BaseModel, Field


CanvasTargetOwner = Literal[
    "canvas_macro",
    "patch_edit_subgraph",
    "construction_subgraph",
    "validation_subgraph",
]


class CanvasDelegationPayloadInput(BaseModel):
    target_owner: CanvasTargetOwner = Field(description="Destination owner for the next canvas task.")
    user_request: str = Field(description="Latest user request being delegated.")
    expected_result: str = Field(description="Concrete output expected from the receiving owner.")
    reason: str = Field(description="Why this owner is responsible.")
    known_context: str = Field(default="", description="Minimal canvas ids, semantic status and constraints.")


@tool(args_schema=CanvasDelegationPayloadInput)
def prepare_canvas_delegation_payload(
    target_owner: CanvasTargetOwner,
    user_request: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Prepare a narrow handoff from Canvas Macro to a canvas subagent. This does
    not edit XML and does not mutate workspace records.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_canvas_delegation_payload",
        entity_type="canvas_delegation",
        summary=expected_result,
        payload={
            "target_owner": target_owner,
            "user_request": user_request,
            "expected_result": expected_result,
            "reason": reason,
            "known_context": known_context,
        },
    )


CANVAS_TOOL_POLICY = """
Canvas Macro tools.

Canvas Macro owns routing and governance for the current BPMN canvas. It should
inspect context, decide whether the request is a local patch, structural
construction, validation, or direct read-only explanation, then delegate narrowly.
Project/process discovery belongs to process agents. Full reconstruction belongs
to the construction subgraph and must preserve ProcessUnderstanding and
BPMNSemanticModel context.
""".strip()

PATCH_EDIT_TOOL_POLICY = """
Patch/Edit subagent tools.

Use only local deterministic BPMN operations through manage_canvas_bpmn_model:
inspect, list_elements, update_element, add_element, delete_element,
connect_elements, reconnect_flow, layout and validate. Do not replace the whole
XML and do not rediscover or remodel the process.
""".strip()

CONSTRUCTION_TOOL_POLICY = """
Process Construction subagent tools.

Use ProcessUnderstanding and BPMNSemanticModel as the semantic source of truth.
For broad creation or reconstruction, prepare/load a review, generate or inspect
the preview, validate it and wait for explicit approval before saving.
Do not infer missing process semantics from raw canvas XML alone.
""".strip()

VALIDATION_TOOL_POLICY = """
Canvas Validation subagent tools.

Validate the current canvas technically and semantically against available
ProcessUnderstanding/BPMNSemanticModel context. Report issues, warnings and next
actions. Do not mutate XML except when explicitly asked only for layout repair.
""".strip()


canvas_macro_tools = [
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_process_semantic_context,
    manage_canvas_bpmn_model,
    prepare_canvas_delegation_payload,
    search_bpmn_preferences,
]


patch_edit_tools = [
    manage_canvas_bpmn_model,
    search_bpmn_preferences,
    remember_bpmn_preference,
]


construction_tools = [
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_process_semantic_context,
    retrieve_process_canvas_traceability_context,
    prepare_canvas_bpmn_review,
    approve_canvas_bpmn_review,
    manage_canvas_bpmn_model,
]


validation_tools = [
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_process_semantic_context,
    retrieve_process_canvas_traceability_context,
    manage_canvas_bpmn_model,
]


def _dedupe_tools(tools: list) -> list:
    seen = set()
    result = []
    for item in tools:
        name = getattr(item, "name", repr(item))
        if name in seen:
            continue
        seen.add(name)
        result.append(item)
    return result


canvas_tools = _dedupe_tools([
    *canvas_macro_tools,
    *patch_edit_tools,
    *construction_tools,
    *validation_tools,
])
