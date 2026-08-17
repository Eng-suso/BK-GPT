from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.consulting.tools import CONSULTING_TOOL_POLICY
from backend.graphs.consulting.state import ConsultingState


def build_consulting_subgraph(tools: list, llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ConsultingState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=CONSULTING_TOOL_POLICY,
    )
