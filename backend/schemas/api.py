from typing import Any, Literal

from pydantic import BaseModel, Field


ApiOrigin = Literal["server", "client", "agent", "tool", "provider"]
TraceEventType = Literal[
    "request_start",
    "request_end",
    "node",
    "tool_start",
    "tool_result",
    "route",
    "first_token",
    "usage",
    "warning",
    "error",
]
StreamEventType = Literal[
    "start",
    "trace",
    "node",
    "tool_start",
    "tool_result",
    "delta",
    "warning",
    "error",
    "done",
]


class ApiError(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Reader-facing error message.")
    detail: str | None = Field(default=None, description="Optional diagnostic detail.")
    request_id: str | None = None
    trace_id: str | None = None
    origin: ApiOrigin = "server"
    retryable: bool = False


class ApiMeta(BaseModel):
    request_id: str
    trace_id: str | None = None
    duration_ms: int | None = None
    warnings: list[str] = Field(default_factory=list)


class ApiEnvelope(BaseModel):
    ok: bool
    data: Any | None = None
    error: ApiError | None = None
    meta: ApiMeta


class TraceContext(BaseModel):
    request_id: str
    trace_id: str
    thread_id: str | None = None
    checkpoint_thread_id: str | None = None
    scope_type: str | None = None
    scope_key: str | None = None
    model_name: str | None = None


class AgentTraceEvent(BaseModel):
    trace_id: str
    event_type: TraceEventType
    node: str | None = None
    route: str | None = None
    tool_name: str | None = None
    status: str = "ok"
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int | None = None


class AgentStreamEvent(BaseModel):
    type: StreamEventType
    request_id: str | None = None
    trace_id: str | None = None
    thread_id: str | None = None
    node: str | None = None
    tool_name: str | None = None
    content: str | None = None
    message: str | None = None
    error: ApiError | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EvalCheckResult(BaseModel):
    name: str
    status: Literal["pass", "fail", "warn"]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class EvalRunResponse(BaseModel):
    ok: bool
    suite: str
    checks: list[EvalCheckResult]
    trace_id: str | None = None
