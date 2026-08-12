import sqlite3

from pathlib import Path
from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from backend.settings import ALLOWED_MODELS, DEFAULT_OPENAI_MODEL, settings
from backend.tools import tools
from backend.memory.procedural.skill_loader import build_skill_context


PROCEDURAL_MEMORY_PATH = Path(__file__).parent / "memory" / "procedural" / "how_to_act.md"
RECENT_MESSAGE_LIMIT = 10
SUMMARY_TRIGGER_MESSAGE_COUNT = 16
SUMMARY_KEEP_RECENT_MESSAGES = 10


class ConsultantState(MessagesState):
    running_summary: str
    summarized_message_count: int
    active_skill_context: str

def load_procedural_memory() -> str:
    return PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8").strip()


def build_context_messages(state: ConsultantState):
    messages = [SystemMessage(content=load_procedural_memory())]
    skill_context = state.get("active_skill_context")

    if skill_context:
        messages.append(SystemMessage(content=skill_context))

    running_summary = state.get("running_summary")

    if running_summary:
        messages.append(
            SystemMessage(
                content=(
                    "Running conversation summary. Use this as compressed "
                    "context from earlier in the thread, not as a substitute "
                    "for the user's latest instructions.\n\n"
                    f"{running_summary}"
                )
            )
        )

    return messages + state["messages"][-RECENT_MESSAGE_LIMIT:]


def message_to_summary_line(message) -> str:
    role = getattr(message, "type", None) or getattr(message, "role", "message")
    content = getattr(message, "content", "")

    if isinstance(content, list):
        content = " ".join(
            str(item.get("text") or item.get("content") or item)
            if isinstance(item, dict)
            else str(item)
            for item in content
        )

    return f"{role}: {str(content).strip()}"


def build_summary_prompt(existing_summary: str, messages_to_summarize: list) -> list:
    transcript = "\n".join(
        line
        for line in (message_to_summary_line(message) for message in messages_to_summarize)
        if line.strip()
    )

    return [
        SystemMessage(
            content=(
                "You maintain the working-memory running summary for a consultant assistant. "
                "Update the summary using only the new conversation messages. Keep it concise, "
                "operational, and useful for future turns. Preserve confirmed decisions, current "
                "goal, constraints, open questions, pending actions, and important context. "
                "Do not invent facts."
            )
        ),
        HumanMessage(
            content=(
                "Existing running summary:\n"
                f"{existing_summary or 'None yet.'}\n\n"
                "New messages to fold into the summary:\n"
                f"{transcript}\n\n"
                "Return the updated running summary with these sections when relevant:\n"
                "Current objective:\n"
                "Confirmed decisions:\n"
                "Important context:\n"
                "Open questions:\n"
                "Pending actions:"
            )
        ),
    ]

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
    skill_selector_llm = ChatOpenAI(
        model=selected_model,
        api_key=settings.openai_api_key,
        temperature=settings.model_temperature,
        max_tokens=256,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=False,
        reasoning_effort="none",
    )

    def summarize_node(state: ConsultantState):
        messages = state["messages"]

        if len(messages) <= SUMMARY_TRIGGER_MESSAGE_COUNT:
            return {}

        cutoff = max(len(messages) - SUMMARY_KEEP_RECENT_MESSAGES, 0)
        summarized_message_count = state.get("summarized_message_count", 0)

        if cutoff <= summarized_message_count:
            return {}

        messages_to_summarize = messages[summarized_message_count:cutoff]

        if not messages_to_summarize:
            return {}

        summary_response = llm.invoke(
            build_summary_prompt(
                existing_summary=state.get("running_summary", ""),
                messages_to_summarize=messages_to_summarize,
            )
        )

        return {
            "running_summary": str(summary_response.content).strip(),
            "summarized_message_count": cutoff,
        }

    def select_skills_node(state: ConsultantState):
        return {
            "active_skill_context": build_skill_context(
                state["messages"],
                selector_llm=skill_selector_llm,
            )
        }

    def chatbot_node(state: ConsultantState):
        messages = build_context_messages(state)
        response = None

        for chunk in llm_with_tools.stream(messages):
            response = chunk if response is None else response + chunk

        return {"messages": [response or AIMessage(content="")]}

    workflow = StateGraph(ConsultantState)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("select_skills", select_skills_node)
    workflow.add_node("chatbot", chatbot_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "summarize")
    workflow.add_edge("summarize", "select_skills")
    workflow.add_edge("select_skills", "chatbot")
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
