from langchain_core.messages import AIMessage
from langchain_core.messages import SystemMessage
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition


class ConversationState(MessagesState):
    running_summary: str
    consultant_context_category: str
    consultant_context_confidence: float
    memory_type: str
    should_save_memory: bool
    suggested_memory_category: str | None
    consultant_context_reason: str
    active_skill_names: list[str]
    skill_selection_reason: str
    active_skill_context: str


def build_tool_chat_subgraph(
    state_schema,
    tools: list,
    llm_with_tools,
    build_context_messages,
    subgraph_contract: str | None = None,
    preload_node=None,
    agent_node_name: str = "chatbot",
    tool_node_name: str = "tools",
):
    def agent_node(state):
        messages = build_context_messages(state)

        if subgraph_contract:
            messages = [*messages, SystemMessage(content=subgraph_contract)]

        response = None

        for chunk in llm_with_tools.stream(messages):
            response = chunk if response is None else response + chunk

        return {"messages": [response or AIMessage(content="")]}

    workflow = StateGraph(state_schema)
    workflow.add_node(agent_node_name, agent_node)
    workflow.add_node(tool_node_name, ToolNode(tools))

    if preload_node is None:
        workflow.add_edge(START, agent_node_name)
    else:
        workflow.add_node("load_context", preload_node)
        workflow.add_edge(START, "load_context")
        workflow.add_edge("load_context", agent_node_name)

    workflow.add_conditional_edges(
        agent_node_name,
        tools_condition,
        {
            "tools": tool_node_name,
            "__end__": END,
        },
    )
    workflow.add_edge(tool_node_name, agent_node_name)
    return workflow.compile()
