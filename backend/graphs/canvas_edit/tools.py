from typing import Literal

from backend.toolsets.bpmn import (
    approve_canvas_bpmn_review,
    manage_canvas_construction,
    manage_canvas_bpmn_model,
    manage_canvas_validation,
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
    "layout_subgraph",
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
BPMNSemanticModel context. Canvas always has access to process semantic context,
BPMN preferences and process-to-canvas traceability memory, including for small
local patches.
""".strip()

PATCH_EDIT_TOOL_POLICY = """
Patch/Edit subagent tools.

Use only local deterministic BPMN operations through manage_canvas_bpmn_model:
inspect, list_elements, update_element, add_element, delete_element,
clear_canvas, connect_elements, reconnect_flow, layout and validate. Do not
replace the whole XML and do not rediscover or remodel the process. If the user
asks to remove every visible canvas element, call clear_canvas directly. If the
user refers to one visible element by label, list_elements first and use the
exact BPMN id from the listed model element; do not do fuzzy/token search and do
not ask for confirmation when there is exactly one structural match. Ask only
when the listed model has no match or multiple plausible matches.
""".strip()

CONSTRUCTION_TOOL_POLICY = """
Process Construction subagent tools.

Use ProcessUnderstanding and BPMNSemanticModel as the semantic source of truth.
For broad creation or reconstruction, prepare/load a review, generate or inspect
the preview, validate it and wait for explicit approval before saving. If the
user supplied a raw process description and no semantic model exists yet, call
prepare_canvas_bpmn_review using that description. Do not infer missing process
semantics from raw canvas XML alone. The visible canvas must stay operational:
show BPMN flow nodes, gateways, lanes and sequence flows; keep rules, unknowns,
data objects, handoffs and traceability in the semantic payload, not as visible
text annotations or data artifacts.
""".strip()

VALIDATION_TOOL_POLICY = """
Canvas Validation subagent tools.

Validate the current canvas technically and semantically against available
ProcessUnderstanding/BPMNSemanticModel context. Report issues, warnings and next
actions. Do not mutate XML except when explicitly asked only for layout repair.
""".strip()

LAYOUT_TOOL_POLICY = """
Canvas Drawing/Layout subagent tools.

Own visual readability only through an explicit consultant-style layout plan:
split the objective into layout tasks, choose readable left-to-right rows, then
draw. Start events should sit on the left, end events should finish to the right,
and branches/retries may use lower rows when that improves readability. Do not
use hidden deterministic fallback layout when the plan is missing or incomplete.
Remove semantic text annotations, association edges and data artifacts from the
visible canvas before layout; they belong in the canonical BPMNSemanticModel
payload. Sequence flows, message flows and labels are not elements for overlap
checks. Do not alter business semantics, labels, owners or sequence flow
source/target. A layout pass should end with layout validation and a saved BPMN
XML version only when the geometry is readable.
""".strip()


canvas_macro_tools = [
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_process_semantic_context,
    manage_canvas_bpmn_model,
    prepare_canvas_delegation_payload,
    search_bpmn_preferences,
    retrieve_process_canvas_traceability_context,
]


patch_edit_tools = [
    manage_canvas_bpmn_model,
    get_process_semantic_context,
    retrieve_process_canvas_traceability_context,
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
    manage_canvas_construction,
    manage_canvas_bpmn_model,
]


validation_tools = [
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    get_process_semantic_context,
    retrieve_process_canvas_traceability_context,
    manage_canvas_validation,
    manage_canvas_bpmn_model,
]


layout_tools = [
    manage_canvas_bpmn_model,
    manage_canvas_validation,
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
    *layout_tools,
    *validation_tools,
])
