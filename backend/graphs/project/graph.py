from backend.graphs.common import build_tool_chat_subgraph
from backend.graphs.project.tools import PROJECT_TOOL_POLICY
from backend.graphs.project.state import ProjectState


def build_project_subgraph(tools: list, llm_with_tools, build_context_messages):
    return build_tool_chat_subgraph(
        state_schema=ProjectState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROJECT_TOOL_POLICY,
    )
