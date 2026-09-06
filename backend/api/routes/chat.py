import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.database import (
    append_chat_message,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_session,
    delete_chat_sessions_by_scope,
    get_chat_session,
    list_chat_sessions,
)
from backend.schemas.api import AgentStreamEvent
from backend.schemas.chat_api import (
    ChatRequest,
    ChatResponse,
    ChatSessionDetail,
    ChatSessionSummary,
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
)
from backend.security import AuthPrincipal, require_admin_principal, require_principal
from backend.services.agent_runtime import (
    build_trace_context,
    scope_fields,
    stream_agent_events,
    stream_agent_text,
)


router = APIRouter(tags=["chat"], dependencies=[Depends(require_principal)])


def ndjson_event(event_type: str, **payload) -> str:
    """Serialize an event and its payload as a newline-delimited JSON record.
    
    Args:
        event_type (str): Untrusted event type included under the ``type`` key.
        **payload: Untrusted event fields included in the serialized record.
    
    Returns:
        str: A JSON object followed by a newline character.
    
    Raises:
        TypeError: If the event type or payload contains a value that cannot be
            serialized as JSON.
    """
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


@router.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Generate a chat response for the requested thread and conversation context.
    
    Args:
        request (ChatRequest): Untrusted chat request containing the thread, model,
            messages, scope, mode, and attachments.
    
    Returns:
        ChatResponse: The generated message associated with the requested thread.
    
    Raises:
        HTTPException: A 502 error if agent execution fails.
    """
    try:
        response_message = stream_agent_text(
            thread_id=request.thread_id,
            model_name=request.model_name,
            messages=request.messages,
            scope=request.scope,
            chat_mode=request.mode,
            attachments=request.attachments,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        thread_id=request.thread_id,
        message=response_message,
    )


@router.post("/v1/consultant-chat/sessions")
def create_consultant_chat_session(request: CreateSessionRequest) -> CreateSessionResponse:
    thread_id = str(uuid4())
    fields = scope_fields(request.scope)
    session = create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
        title=request.title or "Nuova chat",
        **fields,
    )

    return CreateSessionResponse(
        thread_id=session["thread_id"],
        model_name=session["model_name"],
        title=session["title"],
        scope_type=session["scope_type"],
        project_id=session["project_id"],
        process_id=session["process_id"],
        bpmn_model_id=session["bpmn_model_id"],
        scope_key=session["scope_key"],
    )


@router.get("/v1/consultant-chat/sessions")
def get_consultant_chat_sessions(scope_key: str | None = None) -> list[ChatSessionSummary]:
    return [ChatSessionSummary(**session) for session in list_chat_sessions(scope_key=scope_key)]


@router.get("/v1/consultant-chat/sessions/{thread_id}")
def get_consultant_chat_session(thread_id: str) -> ChatSessionDetail:
    session = get_chat_session(thread_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")

    return ChatSessionDetail(**session)


@router.delete("/v1/consultant-chat/sessions")
def clear_consultant_chat_sessions(
    scope_key: str | None = None,
    _principal: AuthPrincipal = Depends(require_admin_principal),
):
    if scope_key:
        delete_chat_sessions_by_scope(scope_key)
    else:
        delete_all_chat_sessions()

    return {"status": "ok"}


@router.delete("/v1/consultant-chat/sessions/{thread_id}")
def remove_consultant_chat_session(
    thread_id: str,
    _principal: AuthPrincipal = Depends(require_admin_principal),
):
    delete_chat_session(thread_id)
    return {"status": "ok"}


@router.post("/v1/consultant-chat/sessions/{thread_id}/messages")
def send_consultant_chat_message(
    thread_id: str,
    request: SendMessageRequest,
) -> ChatResponse:
    """Send a message to a consultant chat session and generate the assistant response.
    
    The chat session and user message are persisted before invoking the agent. A
    successful response is also persisted as an assistant message.
    
    Args:
        thread_id (str): Untrusted chat session identifier.
        request (SendMessageRequest): Untrusted message, model, scope, mode, and
            attachment data.
    
    Returns:
        ChatResponse: The generated assistant message and its thread identifier.
    
    Raises:
        HTTPException: With status 503 if agent processing times out, or status 502
            for other agent-processing failures.
    """
    fields = scope_fields(request.scope)
    create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
        **fields,
    )
    append_chat_message(
        thread_id=thread_id,
        role="user",
        content=request.message,
        model_name=request.model_name,
        **fields,
    )

    try:
        response_message = stream_agent_text(
            thread_id=thread_id,
            model_name=request.model_name,
            messages=[{"role": "user", "content": request.message}],
            scope=request.scope,
            chat_mode=request.mode,
            attachments=request.attachments,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    append_chat_message(
        thread_id=thread_id,
        role="assistant",
        content=response_message,
        model_name=request.model_name,
    )

    return ChatResponse(
        thread_id=thread_id,
        message=response_message,
    )


@router.post("/v1/consultant-chat/sessions/{thread_id}/messages/stream")
def stream_consultant_chat_message(
    thread_id: str,
    request: SendMessageRequest,
):
    """Stream a consultant chat response as newline-delimited JSON events.
    
    The chat session and user message are persisted before streaming begins. The
    response is persisted after successful agent streaming, and the stream emits
    an error event if agent processing or response assembly fails.
    
    Args:
        thread_id: Untrusted session identifier.
        request: Untrusted message, model, scope, mode, and attachment data.
    
    Returns:
        A streaming response containing start, agent, completion, or error events.
    """
    fields = scope_fields(request.scope)
    create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
        **fields,
    )
    append_chat_message(
        thread_id=thread_id,
        role="user",
        content=request.message,
        model_name=request.model_name,
        **fields,
    )

    def generate():
        """
        Stream newline-delimited agent events for the chat request.
        
        The stream emits a start event, forwards agent events, and emits a done event
        after persisting the assembled assistant response. Duplicate start events are
        omitted, and an agent error event ends the stream without persisting a
        response. Exceptions are converted into streamed error events.
        
        Yields:
            str: A newline-delimited JSON event.
        """
        response_parts = []
        trace_context = build_trace_context(
            thread_id=thread_id,
            model_name=request.model_name,
            scope=request.scope,
        )

        try:
            yield AgentStreamEvent(
                type="start",
                request_id=trace_context.request_id,
                trace_id=trace_context.trace_id,
                thread_id=thread_id,
                payload={
                    "scope": fields,
                },
            ).model_dump_json() + "\n"

            for event in stream_agent_events(
                thread_id=thread_id,
                model_name=request.model_name,
                messages=[{"role": "user", "content": request.message}],
                scope=request.scope,
                chat_mode=request.mode,
            attachments=request.attachments,
                trace_context=trace_context,
            ):
                if event.type == "start":
                    continue

                if event.type == "delta" and event.content:
                    response_parts.append(event.content)

                yield event.model_dump_json() + "\n"

                if event.type == "error":
                    return

            response_message = "".join(response_parts)
            append_chat_message(
                thread_id=thread_id,
                role="assistant",
                content=response_message,
                model_name=request.model_name,
            )
            yield AgentStreamEvent(
                type="done",
                request_id=trace_context.request_id,
                trace_id=trace_context.trace_id,
                thread_id=thread_id,
                message=response_message,
            ).model_dump_json() + "\n"
        except Exception as exc:
            yield ndjson_event("error", detail=str(exc))

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
