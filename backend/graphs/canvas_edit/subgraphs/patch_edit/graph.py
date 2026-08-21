from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import tool_prompt_block
from backend.graphs.canvas_edit.subgraphs.patch_edit.state import CanvasPatchEditState
from backend.graphs.canvas_edit.subgraphs.patch_edit.tools import PATCH_EDIT_TOOL_POLICY, patch_edit_tools


PATCH_EDIT_SUBGRAPH_CONTRACT = """
Canvas Patch/Edit subgraph contract.

{tool_policy}

Treat effective_bpmn_xml as the live source of truth. If the user references an
element by label, inspect/list elements first. Keep changes local and validate
after mutation when possible. If the request requires remodelling a significant
process section, explain that Construction must own it instead of replacing XML.

Answer in business language for a non-technical process owner. Say passaggio,
ruolo responsabile, collegamento, punto da verificare. Do not expose XML, ids,
sourceRef, targetRef, node, gateway or sequenceFlow unless explicitly requested.

{tool_prompts}
""".format(
    tool_policy=PATCH_EDIT_TOOL_POLICY,
    tool_prompts=tool_prompt_block(patch_edit_tools),
).strip()


def build_patch_edit_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=CanvasPatchEditState,
        tools=patch_edit_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PATCH_EDIT_SUBGRAPH_CONTRACT,
        agent_node_name="canvas_patch_edit_agent",
        tool_node_name="canvas_patch_edit_tools",
    )
