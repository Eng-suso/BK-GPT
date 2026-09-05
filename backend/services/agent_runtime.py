from __future__ import annotations

from contextlib import nullcontext
import json
import re
from functools import lru_cache
from queue import Empty, Queue
from threading import Lock
from threading import Thread
import time
from typing import Any, Iterator
from uuid import UUID

from backend.agent import get_agent, normalize_model_name
from backend.agents.primary_scope import agent_scope_state
from backend.agents.scope_guard import bind_active_scope
from backend.llm_config import chat_openai_kwargs
from backend.llm_streaming import (
    INTERNAL_STREAM_METADATA_KEY,
    INTERNAL_STREAM_METADATA_VALUE,
    stream_to_text,
)
from backend.schemas.api import AgentStreamEvent, ApiError, TraceContext
from backend.schemas.chat import ChatScope, chat_scope_key
from backend.services.trace_recorder import elapsed_ms, new_trace_context, trace_event
from backend.settings import (
    effective_langsmith_model_name,
    langsmith_metadata,
    langsmith_tags,
    langsmith_tracing_enabled,
    settings,
)

try:
    import langsmith as ls
except ImportError:  # pragma: no cover - langsmith is provided by LangChain deps.
    ls = None


THREAD_LOCK_TIMEOUT_SECONDS = 30
ACTIVITY_HEARTBEAT_SECONDS = 4.0
STREAMABLE_AGENT_NODES = {
    "chatbot",
    "consulting_subgraph",
    "project_subgraph",
    "process_subgraph",
    "canvas_subgraph",
    "home_subgraph",
    "clients_subgraph",
    "setup_subgraph",
    "delivery_subgraph",
    "process_coordination_subgraph",
    "discovery_subgraph",
    "evidence_subgraph",
    "modeling_subgraph",
    "project_macro_agent",
    "project_delivery_agent",
    "project_process_coordination_agent",
    "consult_macro_agent",
    "home_agent",
    "clients_agent",
    "setup_agent",
    "process_agent",
    "process_macro_agent",
    "process_discovery_agent",
    "process_evidence_agent",
    "process_modeling_agent",
    "canvas_agent",
    "canvas_router",
    "canvas_macro_agent",
    "patch_edit_subgraph",
    "canvas_patch_edit_agent",
    "construction_subgraph",
    "canvas_construction_agent",
    "layout_subgraph",
    "canvas_layout_consultant_agent",
    "canvas_drawing_agent",
    "validation_subgraph",
    "canvas_validation_agent",
    "canvas_completion_report",
    "delegate_to_project_macro",
    "delegate_to_process_macro",
    "delegate_to_canvas_macro",
    "ask_consulting_clarification",
    "ask_project_clarification",
    "ask_process_clarification",
    "ask_canvas_clarification",
}
DELTA_STREAM_AGENT_NODES = {
    "chatbot",
    "consulting_subgraph",
    "project_subgraph",
    "process_subgraph",
    "canvas_subgraph",
    "home_subgraph",
    "clients_subgraph",
    "setup_subgraph",
    "delivery_subgraph",
    "process_coordination_subgraph",
    "discovery_subgraph",
    "evidence_subgraph",
    "modeling_subgraph",
    "project_macro_agent",
    "project_delivery_agent",
    "project_process_coordination_agent",
    "consult_macro_agent",
    "home_agent",
    "clients_agent",
    "setup_agent",
    "process_agent",
    "process_macro_agent",
    "process_discovery_agent",
    "process_evidence_agent",
    "process_modeling_agent",
    "canvas_agent",
    "canvas_macro_agent",
    "canvas_patch_edit_agent",
    "canvas_construction_agent",
    "canvas_layout_consultant_agent",
    "canvas_drawing_agent",
    "canvas_validation_agent",
    "canvas_completion_report",
    "delegate_to_project_macro",
    "delegate_to_process_macro",
    "delegate_to_canvas_macro",
    "ask_consulting_clarification",
    "ask_project_clarification",
    "ask_process_clarification",
    "ask_canvas_clarification",
}

_THREAD_LOCKS: dict[str, Lock] = {}
_THREAD_LOCKS_GUARD = Lock()
_ACTIVITY_WORD_RE = re.compile(r"[\w']+")


def merge_usage_metadata(
    totals: dict[str, Any],
    usage_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if not usage_metadata:
        return totals

    for key, value in usage_metadata.items():
        if isinstance(value, bool):
            continue

        if isinstance(value, int | float):
            totals[key] = totals.get(key, 0) + value
            continue

        if isinstance(value, dict):
            nested = totals.setdefault(key, {})
            if isinstance(nested, dict):
                merge_usage_metadata(nested, value)

    return totals


def get_thread_lock(thread_id: str) -> Lock:
    with _THREAD_LOCKS_GUARD:
        if thread_id not in _THREAD_LOCKS:
            _THREAD_LOCKS[thread_id] = Lock()

        return _THREAD_LOCKS[thread_id]


def message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))

        return "".join(parts)

    return str(content or "")


def sanitize_activity_label(value: str) -> str:
    """Visible agent status: no JSON, no hidden reasoning, max five words."""
    text = " ".join(str(value or "").strip().split())
    if not text or "{" in text or "}" in text:
        return ""
    words = _ACTIVITY_WORD_RE.findall(text)
    return " ".join(words[:5])


def activity_icon_for_node(node_name: str | None) -> str:
    node = node_name or ""
    if "layout" in node:
        return "compass"
    if "draw" in node or "canvas" in node:
        return "draw"
    if "validation" in node or "review" in node or "completion" in node:
        return "check"
    if "route" in node or "router" in node:
        return "route"
    if "construction" in node or "modeling" in node:
        return "build"
    if "edit" in node or "patch" in node:
        return "edit"
    return "brain"


def is_internal_stream_metadata(metadata: dict[str, Any]) -> bool:
    if metadata.get(INTERNAL_STREAM_METADATA_KEY) == INTERNAL_STREAM_METADATA_VALUE:
        return True

    nested = metadata.get("metadata")
    if isinstance(nested, dict) and nested.get(INTERNAL_STREAM_METADATA_KEY) == INTERNAL_STREAM_METADATA_VALUE:
        return True

    tags = metadata.get("tags")
    return isinstance(tags, list) and INTERNAL_STREAM_METADATA_VALUE in tags


@lru_cache(maxsize=1)
def _activity_narrator_llm() -> Any | None:
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        kwargs = chat_openai_kwargs(
            max_tokens=18,
            temperature=settings.model_temperature,
            reasoning_effort="low",
            verbosity="low",
        )
        kwargs["timeout"] = min(float(settings.model_timeout_seconds), 6.0)
        kwargs["max_retries"] = 0
        kwargs["streaming"] = True
        kwargs["disable_streaming"] = False
        return ChatOpenAI(**kwargs)
    except Exception:
        return None


def _activity_prompt(
    *,
    user_text: str,
    scope_type: str | None,
    node_name: str | None,
    elapsed_seconds: int,
) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(
            content=(
                "Scrivi solo una micro-frase italiana di massimo 5 parole che dica "
                "cosa sta facendo ora un agente enterprise. Niente JSON, niente "
                "spiegazioni, niente punteggiatura finale, niente dettagli interni. "
                "Non rispondere mai alla richiesta utente: descrivi solo l'azione "
                "in corso. Non salutare. Esempi validi: Analizzo il contesto, "
                "Verifico i passaggi, Coordino i tool."
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "scope": scope_type or "consultant",
                    "current_node": node_name or "agent",
                    "elapsed_seconds": elapsed_seconds,
                    "user_request": user_text[:500],
                },
                ensure_ascii=False,
            )
        ),
    ]


def build_activity_event(
    *,
    context: TraceContext,
    thread_id: str,
    user_text: str,
    node_name: str | None,
    elapsed_seconds: int,
    sequence: int,
) -> AgentStreamEvent | None:
    llm = _activity_narrator_llm()
    if llm is None:
        return None
    try:
        label = sanitize_activity_label(
            stream_to_text(
                llm,
                _activity_prompt(
                    user_text=user_text,
                    scope_type=context.scope_type,
                    node_name=node_name,
                    elapsed_seconds=elapsed_seconds,
                ),
            )
        )
    except Exception:
        return None
    if not label:
        return None
    return AgentStreamEvent(
        type="activity",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        node=node_name,
        message=label,
        payload={
            "activity_id": f"activity-{sequence}",
            "icon": activity_icon_for_node(node_name),
            "source": "llm",
            "max_words": 5,
        },
    )


def agent_checkpoint_thread_id(thread_id: str, scope_key: str | None) -> str:
    return f"{scope_key or 'consultant'}:{thread_id}"


def scope_fields(scope: ChatScope | None) -> dict[str, str | None]:
    key = chat_scope_key(scope)

    if scope is None:
        return {
            "scope_type": "consultant",
            "project_id": None,
            "process_id": None,
            "bpmn_model_id": None,
            "scope_key": key,
        }

    return {
        "scope_type": scope.type,
        "project_id": getattr(scope, "project_id", None),
        "process_id": getattr(scope, "process_id", None),
        "bpmn_model_id": getattr(scope, "bpmn_model_id", None),
        "scope_key": key,
    }


def build_trace_context(
    *,
    thread_id: str,
    model_name: str | None,
    scope: ChatScope | None,
) -> TraceContext:
    """Build trace metadata for a request and its scoped checkpoint thread.
    
    Args:
        thread_id (str): Untrusted request thread identifier.
        model_name (str | None): Model name to associate with the trace.
        scope (ChatScope | None): Optional scope used to derive scope type, scope key,
            and checkpoint thread identity.
    
    Returns:
        TraceContext: Trace context containing the request thread, scoped checkpoint
            thread, scope metadata, and model name.
    """
    fields = scope_fields(scope)
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    return new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )


def _latest_user_message(messages: list[dict]) -> str:
    """Extract the most recent user message content.
    
    Args:
        messages (list[dict]): Untrusted message records to search in reverse order.
    
    Returns:
        str: The stripped content of the most recent user or human message, or an
            empty string when no such message exists.
    """
    for message in reversed(messages or []):
        role = message.get("role") or message.get("type")
        if role in {"user", "human"}:
            return str(message.get("content") or "").strip()
    return ""


def fake_agent_events(
    *,
    thread_id: str,
    messages: list[dict],
    scope: ChatScope | None,
    context: TraceContext,
) -> Iterator[AgentStreamEvent]:
    """Emits a deterministic fake agent stream without invoking an agent graph or language model.
    
    The stream preserves the standard event sequence: start, request-start trace,
    node, token deltas, and request-end trace. It uses the supplied scope and trace
    context consistently across all events and performs no external side effects or
    persistence.
    
    Args:
        thread_id (str): Untrusted thread identifier included in each emitted event.
        messages (list[dict]): Untrusted input messages used to identify the latest
            user message.
        scope (ChatScope | None): Optional scope associated with the request.
        context (TraceContext): Request and trace identifiers attached to each event.
    
    Returns:
        Iterator[AgentStreamEvent]: Deterministic fake agent stream events.
    """
    fields = scope_fields(scope)
    user_text = _latest_user_message(messages)
    reply = (
        f"[fake-llm] Ricevuto in scope '{fields['scope_type']}'. "
        f"Messaggio: {user_text or '(vuoto)'}"
    )

    yield AgentStreamEvent(
        type="start",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload={
            "scope_type": fields["scope_type"],
            "scope_key": fields["scope_key"],
            "fake_llm": True,
        },
    )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_start", message="Fake agent stream started.").model_dump(),
    )
    yield AgentStreamEvent(
        type="node",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        node="fake_agent",
        payload=trace_event(context, "node", node="fake_agent", message="Fake agent node.").model_dump(),
    )
    for token in reply.split(" "):
        yield AgentStreamEvent(
            type="delta",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            node="fake_agent",
            content=token + " ",
        )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_end", message="Fake agent stream completed.").model_dump(),
    )


def stream_agent_events(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
    trace_context: TraceContext | None = None,
    emit_activity: bool = True,
) -> Iterator[AgentStreamEvent]:
    """
    Stream scoped agent responses as structured events.
    
    The stream derives a scope-specific checkpoint thread, preserves a single active
    request per checkpoint thread, and emits lifecycle, node, text, usage, and trace
    events. Agent execution may update checkpoint state. A busy checkpoint produces a
    retryable error event; execution failures produce a non-retryable error event.
    
    Args:
        thread_id: (Untrusted input.) Request conversation identifier.
        model_name: (Untrusted input.) Requested model name, or None for the default
            model.
        messages: (Untrusted input.) Conversation messages supplied to the agent.
        scope: Optional scope used to select the agent and checkpoint namespace.
        trace_context: Optional trace context to use for emitted events.
    
    Yields:
        AgentStreamEvent: Stream lifecycle, node, text-delta, usage, trace, or error
            events.
    """
    fields = scope_fields(scope)
    selected_model = normalize_model_name(model_name)
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    context = trace_context or new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )

    if settings.delir_fake_llm:
        yield from fake_agent_events(
            thread_id=thread_id,
            messages=messages,
            scope=scope,
            context=context,
        )
        return

    agent = get_agent(selected_model, scope_type=fields["scope_type"])
    thread_lock = get_thread_lock(checkpoint_thread_id)
    last_node = None
    first_token_recorded = False
    usage_totals: dict[str, Any] = {}
    latest_state: dict[str, Any] = {
        "node": None,
        "activity_sequence": 0,
        "started_at": time.monotonic(),
        "user_text": _latest_user_message(messages),
    }
    run_tags = langsmith_tags(
        "consultant-chat",
        f"scope:{fields['scope_type']}",
        f"scope_key:{fields['scope_key']}",
    )
    run_metadata = {
        **langsmith_metadata(
            selected_model,
            thread_id=thread_id,
            session_id=thread_id,
            conversation_id=thread_id,
            checkpoint_thread_id=checkpoint_thread_id,
            scope_type=fields["scope_type"],
            scope_key=fields["scope_key"],
            trace_id=context.trace_id,
            request_id=context.request_id,
        ),
        "delir_requested_model_name": model_name or "",
        "delir_model_name": selected_model,
        "delir_effective_langsmith_model_name": effective_langsmith_model_name(selected_model),
    }

    yield AgentStreamEvent(
        type="start",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload={
            "scope_type": fields["scope_type"],
            "scope_key": fields["scope_key"],
            "checkpoint_thread_id": checkpoint_thread_id,
        },
    )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_start", message="Agent stream started.").model_dump(),
    )

    acquired = thread_lock.acquire(timeout=THREAD_LOCK_TIMEOUT_SECONDS)
    if not acquired:
        error = ApiError(
            code="agent_thread_busy",
            message="Sessione occupata. Riprova tra qualche secondo.",
            detail="A previous request is still running for this checkpoint thread.",
            request_id=context.request_id,
            trace_id=context.trace_id,
            origin="agent",
            retryable=True,
        )
        yield AgentStreamEvent(
            type="error",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            error=error,
        )
        yield AgentStreamEvent(
            type="trace",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            payload=trace_event(
                context,
                "error",
                status="error",
                message=error.message,
                payload=error.model_dump(),
            ).model_dump(),
        )
        return

    output_queue: Queue[AgentStreamEvent | None] = Queue()

    def enqueue(event: AgentStreamEvent) -> None:
        output_queue.put(event)

    def run_agent_stream() -> None:
        nonlocal last_node, first_token_recorded, usage_totals
        tracing_context = (
            ls.tracing_context(
                enabled=True,
                project_name=settings.langsmith_project,
                tags=run_tags,
                metadata=run_metadata,
            )
            if ls is not None and langsmith_tracing_enabled()
            else nullcontext()
        )

        try:
            with tracing_context, bind_active_scope(scope):
                events = agent.stream(
                    {
                        "messages": messages,
                        **agent_scope_state(scope),
                    },
                    config={
                        "configurable": {
                            "thread_id": checkpoint_thread_id,
                        },
                        "run_id": UUID(context.trace_id),
                        "run_name": "DeliR scoped agent",
                        "tags": run_tags,
                        "metadata": run_metadata,
                    },
                    stream_mode="messages",
                )

                for event in events:
                    if isinstance(event, tuple):
                        chunk, metadata = event
                    else:
                        chunk, metadata = event, {}

                    node_name = metadata.get("langgraph_node")
                    if node_name and node_name not in STREAMABLE_AGENT_NODES:
                        continue

                    if node_name and node_name != last_node:
                        last_node = node_name
                        latest_state["node"] = node_name
                        node_trace = trace_event(
                            context,
                            "node",
                            node=node_name,
                            message=f"Agent entered node: {node_name}",
                        )
                        enqueue(
                            AgentStreamEvent(
                                type="node",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                node=node_name,
                                payload=node_trace.model_dump(),
                            )
                        )

                    if getattr(chunk, "type", None) not in {"AIMessageChunk", "ai"}:
                        continue

                    usage_metadata = getattr(chunk, "usage_metadata", None)
                    if usage_metadata:
                        merge_usage_metadata(usage_totals, dict(usage_metadata))

                    content = message_content_to_text(getattr(chunk, "content", ""))

                    if is_internal_stream_metadata(metadata):
                        continue

                    if node_name and node_name not in DELTA_STREAM_AGENT_NODES:
                        continue

                    if content and not first_token_recorded:
                        first_token_recorded = True
                        first_token_trace = trace_event(
                            context,
                            "first_token",
                            node=node_name,
                            message="First streamed model token received.",
                            payload={"ttft_ms": elapsed_ms(context.trace_id)},
                        )
                        enqueue(
                            AgentStreamEvent(
                                type="trace",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                payload=first_token_trace.model_dump(),
                            )
                        )

                    if content:
                        enqueue(
                            AgentStreamEvent(
                                type="delta",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                node=node_name,
                                content=content,
                            )
                        )

            if usage_totals:
                enqueue(
                    AgentStreamEvent(
                        type="trace",
                        request_id=context.request_id,
                        trace_id=context.trace_id,
                        thread_id=thread_id,
                        payload=trace_event(
                            context,
                            "usage",
                            message="Aggregated streamed model usage received.",
                            payload={"usage_metadata": usage_totals},
                        ).model_dump(),
                    )
                )

            enqueue(
                AgentStreamEvent(
                    type="trace",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    payload=trace_event(context, "request_end", message="Agent stream completed.").model_dump(),
                )
            )
        except Exception as exc:
            error = ApiError(
                code="agent_stream_failed",
                message="Errore durante l'esecuzione dell'agente.",
                detail=str(exc),
                request_id=context.request_id,
                trace_id=context.trace_id,
                origin="agent",
                retryable=False,
            )
            enqueue(
                AgentStreamEvent(
                    type="error",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    error=error,
                )
            )
            enqueue(
                AgentStreamEvent(
                    type="trace",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    payload=trace_event(
                        context,
                        "error",
                        status="error",
                        message=error.message,
                        payload=error.model_dump(),
                    ).model_dump(),
                )
            )
        finally:
            thread_lock.release()
            output_queue.put(None)

    worker = Thread(target=run_agent_stream, name=f"delir-agent-stream-{context.request_id}", daemon=True)
    worker.start()

    if emit_activity:
        latest_state["activity_sequence"] += 1
        initial_activity = build_activity_event(
            context=context,
            thread_id=thread_id,
            user_text=str(latest_state["user_text"] or ""),
            node_name=None,
            elapsed_seconds=0,
            sequence=int(latest_state["activity_sequence"]),
        )
        if initial_activity is not None:
            yield initial_activity

    while True:
        try:
            queued = output_queue.get(timeout=ACTIVITY_HEARTBEAT_SECONDS)
        except Empty:
            if emit_activity:
                latest_state["activity_sequence"] += 1
                activity = build_activity_event(
                    context=context,
                    thread_id=thread_id,
                    user_text=str(latest_state["user_text"] or ""),
                    node_name=str(latest_state["node"] or "") or None,
                    elapsed_seconds=int(time.monotonic() - float(latest_state["started_at"])),
                    sequence=int(latest_state["activity_sequence"]),
                )
                if activity is not None:
                    yield activity
            continue

        if queued is None:
            break
        yield queued

    worker.join(timeout=1)

    if worker.is_alive():
        yield AgentStreamEvent(
            type="warning",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            message="Agent stream worker still shutting down.",
        )


def stream_agent_deltas(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
) -> Iterator[str]:
    for event in stream_agent_events(
        thread_id=thread_id,
        model_name=model_name,
        messages=messages,
        scope=scope,
        emit_activity=False,
    ):
        if event.type == "delta" and event.content:
            yield event.content
        elif event.type == "error" and event.error:
            raise RuntimeError(event.error.message)


def stream_agent_text(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
) -> str:
    return "".join(
        stream_agent_deltas(
            thread_id=thread_id,
            model_name=model_name,
            messages=messages,
            scope=scope,
        )
    )
