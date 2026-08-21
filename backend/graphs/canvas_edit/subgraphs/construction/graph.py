from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.skill_context import tool_prompt_block
from backend.graphs.canvas_edit.subgraphs.construction.state import CanvasConstructionState
from backend.graphs.canvas_edit.subgraphs.construction.tools import (
    CONSTRUCTION_TOOL_POLICY,
    construction_tools,
)


CONSTRUCTION_SUBGRAPH_CONTRACT = """
Canvas Process Construction subgraph contract.

{tool_policy}

Start from process_understanding and bpmn_semantic_model already loaded in
state. If they are absent or weak, load process semantic context or prepare a
review before attempting construction. Broad changes require preview and
validation; saving requires an approved review or explicit confirmation.

When presenting the work, describe it as a draft or revision of the process
drawing. Use business language and the business_report returned by tools. Do not
show XML, ids, BPMNSemanticModel, ProcessUnderstanding, sourceRef, targetRef,
node, gateway or sequenceFlow unless explicitly requested.

{tool_prompts}
""".format(
    tool_policy=CONSTRUCTION_TOOL_POLICY,
    tool_prompts=tool_prompt_block(construction_tools),
).strip()


def build_construction_subgraph(llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=CanvasConstructionState,
        tools=construction_tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=CONSTRUCTION_SUBGRAPH_CONTRACT,
        agent_node_name="canvas_construction_agent",
        tool_node_name="canvas_construction_tools",
    )
