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
from backend.schemas.chat import ChatScope
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
from backend.workspace_database import approve_bpmn_review, get_bpmn_review


router = APIRouter(tags=["chat"], dependencies=[Depends(require_principal)])


def ndjson_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def is_bpmn_review_approval_text(message: str) -> bool:
    normalized = " ".join(message.lower().strip().replace("\u00ec", "i").split())
    approval_phrases = {
        "ok",
        "okay",
        "si",
        "approva",
        "approvo",
        "procedi",
        "va bene",
        "genera",
        "genera bpmn",
        "approva e genera",
    }

    return normalized in approval_phrases


def approve_pending_bpmn_review_message(scope: ChatScope | None, message: str) -> str | None:
    if scope is None or scope.type != "canvas" or not scope.bpmn_model_id:
        return None

    if not is_bpmn_review_approval_text(message):
        return None

    review = get_bpmn_review(scope.bpmn_model_id)
    if review is None:
        return (
            "Non c'e una review BPMN pendente per questo canvas. "
            "Prima chiedimi di preparare una review BPMN, poi potrai approvarla."
        )

    result = approve_bpmn_review(scope.bpmn_model_id)
    return (
        "Review BPMN approvata. Ho generato e salvato il BPMN nel canvas.\n\n"
        f"Readiness: {result['review']['readiness_score']}/10\n"
        "Il canvas puo ricaricare il modello salvato dal backend."
    )


@router.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        response_message = stream_agent_text(
            thread_id=request.thread_id,
            model_name=request.model_name,
            messages=request.messages,
            scope=request.scope,
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

    direct_response = approve_pending_bpmn_review_message(request.scope, request.message)
    if direct_response is not None:
        append_chat_message(
            thread_id=thread_id,
            role="assistant",
            content=direct_response,
            model_name=request.model_name,
        )
        return ChatResponse(thread_id=thread_id, message=direct_response)

    try:
        response_message = stream_agent_text(
            thread_id=thread_id,
            model_name=request.model_name,
            messages=[{"role": "user", "content": request.message}],
            scope=request.scope,
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

    direct_response = approve_pending_bpmn_review_message(request.scope, request.message)

    def generate():
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

            if direct_response is not None:
                append_chat_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=direct_response,
                    model_name=request.model_name,
                )
                yield AgentStreamEvent(
                    type="delta",
                    request_id=trace_context.request_id,
                    trace_id=trace_context.trace_id,
                    thread_id=thread_id,
                    content=direct_response,
                ).model_dump_json() + "\n"
                yield AgentStreamEvent(
                    type="done",
                    request_id=trace_context.request_id,
                    trace_id=trace_context.trace_id,
                    thread_id=thread_id,
                    message=direct_response,
                ).model_dump_json() + "\n"
                return

            for event in stream_agent_events(
                thread_id=thread_id,
                model_name=request.model_name,
                messages=[{"role": "user", "content": request.message}],
                scope=request.scope,
                trace_context=trace_context,
            ):
                if event.type == "start":
                    continue

                if event.type == "delta" and event.content:
                    response_parts.append(event.content)

                yield event.model_dump_json() + "\n"

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
