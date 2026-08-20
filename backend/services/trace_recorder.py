from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from uuid import uuid4

from backend.schemas.api import AgentTraceEvent, TraceContext


_TRACE_EVENTS: dict[str, list[AgentTraceEvent]] = defaultdict(list)
_TRACE_STARTS: dict[str, float] = {}


def new_trace_context(
    *,
    request_id: str | None = None,
    thread_id: str | None = None,
    checkpoint_thread_id: str | None = None,
    scope_type: str | None = None,
    scope_key: str | None = None,
    model_name: str | None = None,
) -> TraceContext:
    trace_id = str(uuid4())
    context = TraceContext(
        request_id=request_id or str(uuid4()),
        trace_id=trace_id,
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=scope_type,
        scope_key=scope_key,
        model_name=model_name,
    )
    _TRACE_STARTS[trace_id] = perf_counter()
    return context


def elapsed_ms(trace_id: str) -> int:
    started_at = _TRACE_STARTS.get(trace_id)
    if started_at is None:
        return 0
    return int((perf_counter() - started_at) * 1000)


def record_trace_event(event: AgentTraceEvent) -> AgentTraceEvent:
    _TRACE_EVENTS[event.trace_id].append(event)
    return event


def trace_event(
    context: TraceContext,
    event_type: str,
    *,
    node: str | None = None,
    route: str | None = None,
    tool_name: str | None = None,
    status: str = "ok",
    message: str | None = None,
    payload: dict | None = None,
) -> AgentTraceEvent:
    return record_trace_event(
        AgentTraceEvent(
            trace_id=context.trace_id,
            event_type=event_type,
            node=node,
            route=route,
            tool_name=tool_name,
            status=status,
            message=message,
            payload=payload or {},
            elapsed_ms=elapsed_ms(context.trace_id),
        )
    )


def get_trace(trace_id: str) -> list[AgentTraceEvent]:
    return list(_TRACE_EVENTS.get(trace_id, []))


def clear_trace(trace_id: str) -> None:
    _TRACE_EVENTS.pop(trace_id, None)
    _TRACE_STARTS.pop(trace_id, None)
