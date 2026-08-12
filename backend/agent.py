import sqlite3

from pathlib import Path
from langchain_core.messages import AIMessage
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from backend.settings import ALLOWED_MODELS, DEFAULT_OPENAI_MODEL, settings
from backend.tools import tools


PROCEDURAL_MEMORY_PATH = Path(__file__).parent / "memory" / "procedural" / "how_to_act.md"

def load_procedural_memory() -> str:
    return PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8").strip()

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
        api_key=settings.openai_api_key,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=True,
        reasoning_effort="none",
    )

    llm_with_tools = llm.bind_tools(tools)

    def chatbot_node(state: MessagesState):
        messages = [SystemMessage(content=load_procedural_memory())] + state["messages"]
        response = None

        for chunk in llm_with_tools.stream(messages):
            response = chunk if response is None else response + chunk

        return {"messages": [response or AIMessage(content="")]}

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
