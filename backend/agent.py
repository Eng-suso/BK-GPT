import sqlite3

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from backend.settings import ALLOWED_MODELS, DEFAULT_OPENAI_MODEL, settings
from backend.tools import tools


SYSTEM_PROMPT = """
You are the DeliR Consultant Operating Brain.

Your job is to learn how the consultant thinks, sells, delivers, communicates,
and uses DeliR. You understand the consultant broadly, while applying a
specialized BPMN 2.0 / process-consulting layer when the task involves process
mapping, discovery, governance, as-is/to-be analysis, automation, or validation.

Do not reduce every conversation to BPMN. Use the process layer only when the
user intent requires it. Save durable consultant facts and preferences through
memory tools when available.
"""


def normalize_model_name(model_name: str | None = None) -> str:
    if not model_name:
        return settings.openai_model

    model_name = model_name.strip()

    if model_name in ALLOWED_MODELS:
        return model_name

    return DEFAULT_OPENAI_MODEL


def build_agent(model_name: str | None = None):
    selected_model = normalize_model_name(model_name)

    llm = ChatOpenAI(
        model=selected_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=True,
    )

    llm_with_tools = llm.bind_tools(tools)

    def chatbot_node(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("chatbot", chatbot_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "chatbot")
    workflow.add_conditional_edges("chatbot", tools_condition)
    workflow.add_edge("tools", "chatbot")

    conn = sqlite3.connect("data/agent_checkpoint.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return workflow.compile(checkpointer=checkpointer)


_AGENT_CACHE = {}


def get_agent(model_name: str | None = None):
    selected_model = normalize_model_name(model_name)

    if selected_model not in _AGENT_CACHE:
        _AGENT_CACHE[selected_model] = build_agent(selected_model)

    return _AGENT_CACHE[selected_model]
