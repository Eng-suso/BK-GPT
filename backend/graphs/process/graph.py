from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.process.nodes import load_process_context
from backend.graphs.process.state import ProcessState
from backend.graphs.process.tools import PROCESS_TOOL_POLICY


PROCESS_SUBGRAPH_CONTRACT = """
Process graph contract.

{tool_policy}

ProcessUnderstanding and BPMNSemanticModel are mandatory for AS-IS/BPMN work.
When the user asks to model, review, generate, or validate an AS-IS process,
do not produce BPMN directly from free text. Use the process BPMN review flow,
which must extract ProcessUnderstanding first and derive BPMNSemanticModel from it.

The process chat prepares the review and missing information. It does not approve
or save final BPMN XML unless the active toolset explicitly supports that action.

Before answering, this subgraph loads the current process record, pending review,
ProcessUnderstanding, BPMNSemanticModel, missing information and saved BPMN XML
when available. Use those state artifacts before asking the user to repeat context.
""".format(tool_policy=PROCESS_TOOL_POLICY).strip()


def build_process_subgraph(tools: list, llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProcessState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROCESS_SUBGRAPH_CONTRACT,
        preload_node=load_process_context,
        agent_node_name="process_agent",
        tool_node_name="process_tools",
    )
