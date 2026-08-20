import sqlite3

from pathlib import Path
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, END, StateGraph, MessagesState

from backend.agents.primary_scope import build_scope_system_prompt, tool_scope_type
from backend.graphs.canvas_edit import build_canvas_subgraph
from backend.graphs.consulting import build_consulting_subgraph
from backend.graphs.process import build_process_subgraph
from backend.graphs.project import build_project_subgraph
from backend.settings import ALLOWED_MODELS, DEFAULT_OPENAI_MODEL, settings
from backend.tools import tools_by_scope
from backend.memory.consultant_context_classifier import (
    classify_and_select_context,
    format_classification_context,
)


PROCEDURAL_MEMORY_PATH = Path(__file__).parent / "memory" / "procedural" / "how_to_act.md"
RECENT_MESSAGE_LIMIT = 8
SUMMARY_TRIGGER_MESSAGE_COUNT = 10
SUMMARY_KEEP_RECENT_MESSAGES = 6


class ConsultantState(MessagesState):
    scope_type: str
    scope_key: str
    project_id: str | None
    process_id: str | None
    bpmn_model_id: str | None
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding_json: dict | str | None
    bpmn_semantic_model_json: dict | str | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None
    running_summary: str
    summarized_message_count: int
    consultant_context_category: str
    consultant_context_confidence: float
    memory_type: str
    should_save_memory: bool
    suggested_memory_category: str | None
    consultant_context_reason: str
    active_skill_names: list[str]
    skill_selection_reason: str
    active_skill_context: str

def load_procedural_memory() -> str:
    return PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8").strip()


def build_context_messages(state: ConsultantState):
    messages = [
        SystemMessage(content=load_procedural_memory()),
        SystemMessage(content=build_scope_system_prompt(state)),
    ]
    classification_context = format_classification_context(state)
    skill_context = state.get("active_skill_context")

    if classification_context:
        messages.append(SystemMessage(content=classification_context))

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

    context_router_llm = ChatOpenAI(
        model=selected_model,
        api_key=settings.openai_api_key,
        temperature=settings.model_temperature,
        max_tokens=512,
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

        # Trim old messages from the checkpoint to prevent unbounded growth.
        # After summarization, the content of old messages is captured in
        # running_summary, so we can safely remove them from state.
        remove_ops = [
            RemoveMessage(id=m.id)
            for m in messages[:cutoff]
            if hasattr(m, "id") and m.id
        ]

        return {
            "running_summary": str(summary_response.content).strip(),
            "summarized_message_count": 0,
            **({
                "messages": remove_ops,
            } if remove_ops else {}),
        }

    def classify_and_select_context_node(state: ConsultantState):
        return classify_and_select_context(
            state["messages"],
            classifier_llm=context_router_llm,
        )

    def route_scope(state: ConsultantState):
        return tool_scope_type(state.get("scope_type"))

    workflow = StateGraph(ConsultantState)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("classify_and_select_context", classify_and_select_context_node)
    workflow.add_node(
        "consulting_subgraph",
        build_consulting_subgraph(
            tools=tools_by_scope["consultant"],
            llm=llm,
            llm_with_tools=llm.bind_tools(tools_by_scope["consultant"]),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "project_subgraph",
        build_project_subgraph(
            tools=tools_by_scope["project"],
            llm=llm,
            llm_with_tools=llm.bind_tools(tools_by_scope["project"]),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "process_subgraph",
        build_process_subgraph(
            tools=tools_by_scope["process"],
            llm_with_tools=llm.bind_tools(tools_by_scope["process"]),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "canvas_subgraph",
        build_canvas_subgraph(
            tools=tools_by_scope["canvas"],
            llm_with_tools=llm.bind_tools(tools_by_scope["canvas"]),
            build_context_messages=build_context_messages,
        ),
    )

    workflow.add_edge(START, "summarize")
    workflow.add_edge("summarize", "classify_and_select_context")
    workflow.add_conditional_edges(
        "classify_and_select_context",
        route_scope,
        {
            "consultant": "consulting_subgraph",
            "project": "project_subgraph",
            "process": "process_subgraph",
            "canvas": "canvas_subgraph",
        },
    )
    workflow.add_edge("consulting_subgraph", END)
    workflow.add_edge("project_subgraph", END)
    workflow.add_edge("process_subgraph", END)
    workflow.add_edge("canvas_subgraph", END)

    conn = sqlite3.connect("data/agent_checkpoint.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return workflow.compile(checkpointer=checkpointer)


_AGENT_CACHE = {}


def get_agent(model_name: str | None = None, scope_type: str | None = None):
    selected_model = normalize_model_name(model_name)
    cache_key = selected_model

    if cache_key not in _AGENT_CACHE:
        _AGENT_CACHE[cache_key] = build_agent(selected_model)

    return _AGENT_CACHE[cache_key]
