from backend.graphs.canvas_edit.state import CanvasState
from backend.graphs.canvas_edit.nodes import load_canvas_context
from backend.graphs.canvas_edit.tools import CANVAS_TOOL_POLICY
from backend.graphs.common import build_tool_chat_subgraph


CANVAS_SUBGRAPH_CONTRACT = """
Canvas graph contract.

{tool_policy}

ProcessUnderstanding and BPMNSemanticModel are mandatory for BPMN canvas changes.
The canvas may save full BPMN XML only from a pending review, a validated semantic
model, or an explicit user-approved XML replacement. Do not invent complete BPMN
XML directly in chat text.

For targeted edits to an existing element, use deterministic canvas tools:
first list elements when the element_id is uncertain, then update the element by
id. Targeted edits may change labels/documentation without regenerating the whole
model.

For generated AS-IS/canvas changes, prepare or load the review first, keep missing
information visible, and approve/save only when a bpmn_model_id is present and the
user has clearly approved the pending review.

When current_bpmn_xml is present in state, treat it as the live canvas source of
truth for read/explain/inspect requests, even if the backend saved XML is empty
or older.

Before answering, this subgraph loads pending review artifacts, saved backend XML,
and live canvas XML into state. Use effective_bpmn_xml as the current canvas source
and effective_bpmn_xml_source to explain whether it came from the live UI or saved backend.
""".format(tool_policy=CANVAS_TOOL_POLICY).strip()


def build_canvas_subgraph(tools: list, llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=CanvasState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=CANVAS_SUBGRAPH_CONTRACT,
        preload_node=load_canvas_context,
        agent_node_name="canvas_agent",
        tool_node_name="canvas_tools",
    )
