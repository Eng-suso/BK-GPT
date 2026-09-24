import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.agents.product_language import internal_language_leaks
from backend.database import (
    append_chat_message,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_session,
    delete_chat_sessions_by_scope,
    get_chat_session,
    list_chat_sessions,
    search_chat_sessions,
)
from backend.schemas.api import AgentStreamEvent
from backend.schemas.chat_api import (
    ChatRequest,
    ChatResponse,
    ChatSessionDetail,
    ChatSessionSearchHit,
    ChatSessionSummary,
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
)
from backend.security import AuthPrincipal, require_admin_principal, require_principal
from backend.services import degradation_counters
from backend.services.agent_runtime import (
    build_trace_context,
    scope_fields,
    stream_agent_events,
    stream_agent_text,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(require_principal)])

#: Cosa legge il consulente quando l'agente non ce la fa. Il perche' sta nei
#: log, non nella schermata: `str(exc)` di un'eccezione qualunque porta in
#: interfaccia nomi di provider, frammenti di SQL e percorsi di file, e a chi
#: legge non dice niente che possa usare.
AGENT_FAILED_MESSAGE = (
    "Non sono riuscito a completare questa richiesta. Riprova; se continua, "
    "serve un occhio ai log."
)
AGENT_TIMEOUT_MESSAGE = (
    "La richiesta ha superato il tempo massimo. Riprova, magari chiedendo una "
    "cosa per volta."
)


def log_agent_failure(exc: BaseException, *, thread_id: str, trace_id: str | None = None) -> None:
    """Manda l'eccezione vera dove si puo' leggere: i log, con come ritrovarla."""
    logger.exception(
        "turno di chat fallito (thread=%s trace=%s): %s",
        thread_id,
        trace_id or "-",
        type(exc).__name__,
    )


def record_product_language(*, answer: str, asked: str, scope_type: str | None) -> list[str]:
    """Segna quando la risposta al consulente parla ancora da sistema.

    PROCESS-V2-01. Il contratto di lingua sta nel prompt, quindi la regola vive
    nel modello: senza un contatore, una regressione di linguaggio si vede solo
    quando la nota il consulente. Qui non si riscrive niente - riscrivere la
    risposta a valle nasconderebbe il difetto invece di misurarlo.

    Args:
        answer: Testo consegnato al consulente.
        asked: Messaggio del consulente in questo turno.
        scope_type: Scope della chat, per sapere dove sta perdendo.

    Returns:
        list[str]: Famiglie di vocabolario interno trovate, vuota se pulita.
    """
    leaks = internal_language_leaks(answer, consultant_asked=asked)
    if leaks:
        degradation_counters.bump(
            "product_language",
            "internal_leak",
            detail=f"scope={scope_type or 'consultant'} terms={','.join(leaks)}",
        )
    return leaks


#: Cosa si legge sotto una risposta che non e' arrivata in fondo. Va scritto,
#: non dedotto: riaperto domani, un pensiero troncato a meta' frase sembra un
#: pensiero finito, e in un verbale di consulenza questo e' un danno.
INTERRUPTED_ANSWER_MARKER = (
    "\n\n---\n*Risposta interrotta: il collegamento si e' chiuso mentre l'agente "
    "scriveva.*"
)


def persist_interrupted_answer(
    *,
    thread_id: str,
    parts: list[str],
    model_name: str | None,
) -> bool:
    """Salva quello che l'agente aveva gia' scritto quando il turno si e' rotto.

    Args:
        thread_id: La conversazione a cui appartiene il turno.
        parts: I pezzi di testo gia' arrivati. Vuoti o soli spazi: niente da
            salvare, e una risposta vuota in archivio sarebbe peggio del nulla.
        model_name: Il modello del turno, per la riga in archivio.

    Returns:
        bool: Se qualcosa e' stato scritto.
    """
    partial = "".join(parts).strip()
    if not partial:
        return False

    append_chat_message(
        thread_id=thread_id,
        role="assistant",
        content=f"{partial}{INTERRUPTED_ANSWER_MARKER}",
        model_name=model_name,
    )
    return True


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
        log_agent_failure(exc, thread_id=request.thread_id)
        raise HTTPException(status_code=502, detail=AGENT_FAILED_MESSAGE) from exc

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


# Prima di `/sessions/{thread_id}`: FastAPI prova le rotte in ordine di
# dichiarazione, e piu' in basso "search" sarebbe letto come un thread_id.
@router.get("/v1/consultant-chat/sessions/search")
def search_consultant_chat_sessions(
    q: str,
    scope_key: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[ChatSessionSearchHit]:
    """Cerca fra le conversazioni per titolo e per testo scambiato.

    Args:
        q: Il testo cercato. Vuoto restituisce una lista vuota, non tutto: una
            ricerca senza parole non e' la cronologia.
        scope_key: Limita alla superficie da cui la ricerca e' partita.
        limit: Quante conversazioni restituire.
    """
    return [
        ChatSessionSearchHit(**session)
        for session in search_chat_sessions(q, scope_key=scope_key, limit=limit)
    ]


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
        log_agent_failure(exc, thread_id=thread_id)
        raise HTTPException(status_code=503, detail=AGENT_TIMEOUT_MESSAGE) from exc
    except Exception as exc:
        log_agent_failure(exc, thread_id=thread_id)
        raise HTTPException(status_code=502, detail=AGENT_FAILED_MESSAGE) from exc

    record_product_language(
        answer=response_message,
        asked=request.message,
        scope_type=fields.get("scope_type"),
    )
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

    return StreamingResponse(
        chat_turn_events(thread_id=thread_id, request=request, fields=fields),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def chat_turn_events(
    *,
    thread_id: str,
    request: SendMessageRequest,
    fields: dict,
):
    """Gli eventi di un turno, dall'inizio alla fine o a dove arriva.

    Sta fuori dalla rotta perche' il caso che conta e' quello in cui il turno
    non arriva in fondo, e un generatore con un nome si puo' chiudere in un
    test; dentro una closure, no.

    Args:
        thread_id: La conversazione.
        request: Messaggio, modello, scope, modalita' e allegati del turno.
        fields: Lo scope gia' normalizzato, come lo vede l'archivio.

    Yields:
        str: Un evento JSON per riga.
    """
    response_parts: list[str] = []
    persisted = False
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
        record_product_language(
            answer=response_message,
            asked=request.message,
            scope_type=fields.get("scope_type"),
        )
        append_chat_message(
            thread_id=thread_id,
            role="assistant",
            content=response_message,
            model_name=request.model_name,
        )
        persisted = True
        yield AgentStreamEvent(
            type="done",
            request_id=trace_context.request_id,
            trace_id=trace_context.trace_id,
            thread_id=thread_id,
            message=response_message,
        ).model_dump_json() + "\n"
    except Exception as exc:
        log_agent_failure(exc, thread_id=thread_id, trace_id=trace_context.trace_id)
        yield ndjson_event(
            "error",
            detail=AGENT_FAILED_MESSAGE,
            trace_id=trace_context.trace_id,
        )
    finally:
        # Il turno puo' finire senza arrivare in fondo: il consulente chiude la
        # scheda, preme Stop, o l'agente fallisce a meta' frase. In tutti e tre
        # i casi il salvataggio stava dopo il ciclo e non veniva eseguito - la
        # chiusura del generatore alza `GeneratorExit`, che non e' una
        # `Exception` e quindi non passava nemmeno di qui. Restava una domanda
        # in archivio senza la sua risposta.
        if not persisted:
            persist_interrupted_answer(
                thread_id=thread_id,
                parts=response_parts,
                model_name=request.model_name,
            )

