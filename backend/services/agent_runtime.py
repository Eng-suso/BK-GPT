from __future__ import annotations

from threading import Lock
from typing import Iterator

from backend.agent import get_agent
from backend.agents.primary_scope import agent_scope_state
from backend.schemas.api import AgentStreamEvent, ApiError, TraceContext
from backend.schemas.chat import ChatScope, chat_scope_key
from backend.services.trace_recorder import new_trace_context, trace_event


THREAD_LOCK_TIMEOUT_SECONDS = 30
STREAMABLE_AGENT_NODES = {
    "chatbot",
    "consulting_subgraph",
    "project_subgraph",
    "process_subgraph",
    "canvas_subgraph",
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
    "delegate_to_project_macro",
    "delegate_to_process_macro",
    "delegate_to_canvas_macro",
}

_THREAD_LOCKS: dict[str, Lock] = {}
_THREAD_LOCKS_GUARD = Lock()


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
    fields = scope_fields(scope)
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    return new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )


def stream_agent_events(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
    trace_context: TraceContext | None = None,
) -> Iterator[AgentStreamEvent]:
    fields = scope_fields(scope)
    agent = get_agent(model_name, scope_type=fields["scope_type"])
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    context = trace_context or new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )
    thread_lock = get_thread_lock(checkpoint_thread_id)
    last_node = None

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

    try:
        events = agent.stream(
            {
                "messages": messages,
                **agent_scope_state(scope),
            },
            config={
                "configurable": {
                    "thread_id": checkpoint_thread_id,
                },
                "run_name": "DeliR scoped agent",
                "tags": [
                    f"scope:{fields['scope_type']}",
                    f"scope_key:{fields['scope_key']}",
                ],
                "metadata": {
                    "thread_id": thread_id,
                    "checkpoint_thread_id": checkpoint_thread_id,
                    "scope_type": fields["scope_type"],
                    "scope_key": fields["scope_key"],
                    "model_name": model_name,
                    "trace_id": context.trace_id,
                    "request_id": context.request_id,
                },
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
                node_trace = trace_event(
                    context,
                    "node",
                    node=node_name,
                    message=f"Agent entered node: {node_name}",
                )
                yield AgentStreamEvent(
                    type="node",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    node=node_name,
                    payload=node_trace.model_dump(),
                )

            if getattr(chunk, "type", None) not in {"AIMessageChunk", "ai"}:
                continue

            content = message_content_to_text(getattr(chunk, "content", ""))

            if content:
                yield AgentStreamEvent(
                    type="delta",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    node=node_name,
                    content=content,
                )

        yield AgentStreamEvent(
            type="trace",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            payload=trace_event(context, "request_end", message="Agent stream completed.").model_dump(),
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
    finally:
        thread_lock.release()


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
