from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import tool_prompt_block
from backend.graphs.canvas_edit.subgraphs.validation.state import CanvasValidationState
from backend.graphs.canvas_edit.subgraphs.validation.tools import VALIDATION_TOOL_POLICY, validation_tools


VALIDATION_SUBGRAPH_CONTRACT = """
Canvas Validation subgraph contract.

{tool_policy}

Validate the current effective_bpmn_xml first. When semantic context is present,
compare the canvas against ProcessUnderstanding and BPMNSemanticModel: start/end,
actors/lanes, gateways, alternative paths, handoffs, loops, exceptions and
evidence traceability. Return a concise validation report with issues, warnings
and next actions.

Use the business_report returned by validation tools for the user-facing answer.
Say problemi da correggere, punti da verificare and prossime azioni. Do not
expose XML, ids, sourceRef, targetRef, node, gateway, sequenceFlow,
BPMNSemanticModel or ProcessUnderstanding unless explicitly requested.

{tool_prompts}
""".format(
    tool_policy=VALIDATION_TOOL_POLICY,
    tool_prompts=tool_prompt_block(validation_tools),
).strip()


def build_validation_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=CanvasValidationState,
        tools=validation_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=VALIDATION_SUBGRAPH_CONTRACT,
        agent_node_name="canvas_validation_agent",
        tool_node_name="canvas_validation_tools",
    )
