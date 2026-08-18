import asyncio
import json
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Iterator
from uuid import uuid4
from backend.settings import settings


import websockets
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from backend.agents.primary_scope import agent_scope_state
from backend.agent import get_agent
from backend.database import (
    append_chat_message,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_sessions_by_scope,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
)
from backend.memory.semantic.semantic_store import (
    save_consultant_memory,
    search_consultant_memory,
)
from backend.schemas.chat import ChatScope, chat_scope_key
from backend.schemas.workspace import (
    ApproveBpmnReviewResponse,
    BpmnModelResponse,
    BpmnReviewResponse,
    BpmnVersionResponse,
    ClientResponse,
    CreateClientRequest,
    CreateProcessRequest,
    CreateProjectDecisionRequest,
    CreateProjectRequest,
    CreateProjectSourceRequest,
    ProjectDecisionResponse,
    ProjectProcessResponse,
    ProjectResponse,
    ProjectSourceResponse,
    RestoreBpmnVersionResponse,
    UpdateBpmnModelRequest,
)
from backend.workspace_database import (
    approve_bpmn_review,
    create_client,
    create_process,
    create_project,
    create_project_decision,
    create_project_source,
    get_bpmn_model,
    get_bpmn_review,
    get_process,
    get_project,
    list_bpmn_versions,
    list_clients,
    list_project_decisions,
    list_project_processes,
    list_project_sources,
    list_projects,
    reset_workspace,
    restore_bpmn_version,
    update_bpmn_model,
)

from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    FRONTEND_INDEX = DIST_DIR / "index.html"
    if (DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
else:
    FRONTEND_INDEX = FRONTEND_DIR / "index.html"

if (FRONTEND_DIR / "styles").exists():
    app.mount("/styles", StaticFiles(directory=FRONTEND_DIR / "styles"), name="styles")
if (FRONTEND_DIR / "src").exists():
    app.mount("/src", StaticFiles(directory=FRONTEND_DIR / "src"), name="src")

_THREAD_LOCKS: dict[str, Lock] = {}
_THREAD_LOCKS_GUARD = Lock()
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
THREAD_LOCK_TIMEOUT_SECONDS = 30
STREAMABLE_AGENT_NODES = {
    "chatbot",
    "consulting_subgraph",
    "project_subgraph",
    "process_subgraph",
    "canvas_subgraph",
    "process_agent",
    "canvas_agent",
    "chatbot",
}


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


def stream_agent_deltas(
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
) -> Iterator[str]:
    fields = scope_fields(scope)
    agent = get_agent(model_name, scope_type=fields["scope_type"])
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    thread_lock = get_thread_lock(checkpoint_thread_id)

    acquired = thread_lock.acquire(timeout=THREAD_LOCK_TIMEOUT_SECONDS)
    if not acquired:
        raise TimeoutError(
            "Sessione occupata — una richiesta precedente è ancora in corso. "
            "Riprova tra qualche secondo."
        )

    try:
        events = agent.stream(
            {
                "messages": messages,
                **agent_scope_state(scope),
            },
            config={
                "configurable": {
                    "thread_id": checkpoint_thread_id,
                }
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

            if getattr(chunk, "type", None) not in {"AIMessageChunk", "ai"}:
                continue

            content = message_content_to_text(getattr(chunk, "content", ""))

            if content:
                yield content
    finally:
        thread_lock.release()


def stream_agent_text(
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


def ndjson_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


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


def is_bpmn_review_approval_text(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split())
    approval_phrases = {
        "ok",
        "okay",
        "si",
        "sì",
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
            "Non c'è una review BPMN pendente per questo canvas. "
            "Prima chiedimi di preparare una review BPMN, poi potrai approvarla."
        )

    result = approve_bpmn_review(scope.bpmn_model_id)
    return (
        "Review BPMN approvata. Ho generato e salvato il BPMN nel canvas.\n\n"
        f"Readiness: {result['review']['readiness_score']}/10\n"
        "Il canvas può ricaricare il modello salvato dal backend."
    )


class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]  # List of messages, each message is a dict with 'role' and 'content'
    thread_id: str
    scope: ChatScope | None = None


class CreateSessionRequest(BaseModel):
    model_name: str | None = None
    title: str | None = None
    scope: ChatScope | None = None


class CreateSessionResponse(BaseModel):
    thread_id: str
    model_name: str | None = None
    title: str = "Nuova chat"
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None


class ChatMessageRecord(BaseModel):
    id: int | None = None
    role: str
    content: str
    created_at: str | None = None


class ChatSessionSummary(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatSessionDetail(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None
    created_at: str
    updated_at: str
    messages: list[ChatMessageRecord]


class SendMessageRequest(BaseModel):
    message: str
    model_name: str | None = None
    scope: ChatScope | None = None


class ChatResponse(BaseModel):
    thread_id: str
    message: str


class SaveMemoryRequest(BaseModel):
    content: str
    category: str


class SearchMemoryRequest(BaseModel):
    query: str
    category: str | None = None


class TranscriptionResponse(BaseModel):
    text: str
    model: str
    segments: list[dict[str, Any]] = []
    duration: float | None = None


def openai_object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()

    if isinstance(value, dict):
        return value

    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def format_diarized_transcript(payload: dict[str, Any]) -> str:
    segments = payload.get("segments")

    if not isinstance(segments, list) or not segments:
        return str(payload.get("text") or "").strip()

    lines = []

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        speaker = str(segment.get("speaker") or "Speaker").strip()
        text = str(segment.get("text") or "").strip()

        if text:
            lines.append(f"{speaker}: {text}")

    return "\n".join(lines).strip() or str(payload.get("text") or "").strip()


async def send_ws_event(websocket: WebSocket, event_type: str, **payload) -> None:
    await websocket.send_text(json.dumps({"type": event_type, **payload}, ensure_ascii=False))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    fields = scope_fields(request.scope)

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


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default="it"),
) -> TranscriptionResponse:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY non configurata.")

    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="File audio vuoto.")

    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File audio troppo grande.")

    filename = file.filename or "audio.webm"
    content_type = file.content_type or "application/octet-stream"
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        transcription_options = {
            "file": (filename, audio_file, content_type),
            "model": settings.openai_transcription_model,
            "language": language or None,
        }

        if settings.openai_transcription_model == "gpt-4o-transcribe-diarize":
            transcription_options["response_format"] = "diarized_json"
            transcription_options["chunking_strategy"] = "auto"

        transcription = client.audio.transcriptions.create(**transcription_options)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = openai_object_to_dict(transcription)

    return TranscriptionResponse(
        text=format_diarized_transcript(payload),
        model=settings.openai_transcription_model,
        segments=payload.get("segments") if isinstance(payload.get("segments"), list) else [],
        duration=payload.get("duration") if isinstance(payload.get("duration"), (float, int)) else None,
    )


@app.websocket("/v1/audio/live-transcription")
async def live_audio_transcription(websocket: WebSocket):
    await websocket.accept()

    if not settings.openai_api_key:
        await send_ws_event(websocket, "error", detail="OPENAI_API_KEY non configurata.")
        await websocket.close(code=1011)
        return

    openai_url = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
    }

    try:
        async with websockets.connect(
            openai_url,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
        ) as openai_ws:
            commit_lock = asyncio.Lock()
            has_uncommitted_audio = False

            async def commit_audio_buffer() -> None:
                nonlocal has_uncommitted_audio

                async with commit_lock:
                    if not has_uncommitted_audio:
                        return

                    try:
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    except websockets.exceptions.ConnectionClosed:
                        return

                    has_uncommitted_audio = False

            await openai_ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {
                                        "type": "audio/pcm",
                                        "rate": 24000,
                                    },
                                    "transcription": {
                                        "model": settings.openai_live_transcription_model,
                                    },
                                    "turn_detection": None,
                                }
                            },
                        },
                    }
                )
            )
            await send_ws_event(
                websocket,
                "ready",
                model=settings.openai_live_transcription_model,
                sample_rate=24000,
            )

            async def forward_client_audio():
                nonlocal has_uncommitted_audio

                while True:
                    message = await websocket.receive_text()
                    event = json.loads(message)
                    event_type = event.get("type")

                    if event_type == "audio":
                        audio = event.get("audio")
                        if audio:
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": audio,
                                    }
                                )
                            )
                            has_uncommitted_audio = True
                    elif event_type == "commit":
                        await commit_audio_buffer()
                    elif event_type == "close":
                        await commit_audio_buffer()
                        await openai_ws.close()
                        break

            async def commit_live_audio_periodically():
                while True:
                    await asyncio.sleep(1.5)
                    await commit_audio_buffer()

            async def forward_openai_events():
                async for raw_message in openai_ws:
                    event = json.loads(raw_message)
                    event_type = event.get("type")

                    if event_type == "conversation.item.input_audio_transcription.delta":
                        await send_ws_event(
                            websocket,
                            "delta",
                            delta=event.get("delta", ""),
                            item_id=event.get("item_id"),
                        )
                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        await send_ws_event(
                            websocket,
                            "completed",
                            transcript=event.get("transcript", ""),
                            item_id=event.get("item_id"),
                        )
                    elif event_type == "conversation.item.input_audio_transcription.failed":
                        error = event.get("error") or {}
                        await send_ws_event(
                            websocket,
                            "error",
                            detail=error.get("message") or "Trascrizione live non riuscita.",
                        )
                    elif event_type == "error":
                        error = event.get("error") or {}
                        await send_ws_event(
                            websocket,
                            "error",
                            detail=error.get("message") or "Errore OpenAI Realtime.",
                        )

            client_task = asyncio.create_task(forward_client_audio())
            openai_task = asyncio.create_task(forward_openai_events())
            commit_task = asyncio.create_task(commit_live_audio_periodically())
            done, pending = await asyncio.wait(
                {client_task, openai_task, commit_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            await asyncio.gather(*pending, return_exceptions=True)

            for task in done:
                exception = task.exception()
                if exception and not isinstance(exception, WebSocketDisconnect):
                    raise exception
    except websockets.exceptions.ConnectionClosed as exc:
        try:
            await send_ws_event(
                websocket,
                "error",
                detail=f"OpenAI Realtime ha chiuso la connessione: {exc}",
            )
        except Exception:
            pass
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await send_ws_event(websocket, "error", detail=str(exc))
        except Exception:
            pass


@app.post("/v1/consultant-chat/sessions")
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


@app.get("/v1/consultant-chat/sessions")
def get_consultant_chat_sessions(scope_key: str | None = None) -> list[ChatSessionSummary]:
    return [ChatSessionSummary(**session) for session in list_chat_sessions(scope_key=scope_key)]


@app.get("/v1/consultant-chat/sessions/{thread_id}")
def get_consultant_chat_session(thread_id: str) -> ChatSessionDetail:
    session = get_chat_session(thread_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")

    return ChatSessionDetail(**session)


@app.delete("/v1/consultant-chat/sessions")
def clear_consultant_chat_sessions(scope_key: str | None = None):
    if scope_key:
        delete_chat_sessions_by_scope(scope_key)
    else:
        delete_all_chat_sessions()

    return {"status": "ok"}


@app.delete("/v1/consultant-chat/sessions/{thread_id}")
def remove_consultant_chat_session(thread_id: str):
    delete_chat_session(thread_id)
    return {"status": "ok"}


@app.get("/v1/workspace/clients")
def get_workspace_clients() -> list[ClientResponse]:
    return [ClientResponse(**client) for client in list_clients()]


@app.post("/v1/workspace/clients")
def create_workspace_client(request: CreateClientRequest) -> ClientResponse:
    try:
        return ClientResponse(**create_client(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/workspace/projects")
def get_workspace_projects() -> list[ProjectResponse]:
    return [ProjectResponse(**project) for project in list_projects()]


@app.post("/v1/workspace/projects")
def create_workspace_project(request: CreateProjectRequest) -> ProjectResponse:
    try:
        return ProjectResponse(**create_project(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/workspace/projects/{project_id}")
def get_workspace_project(project_id: str) -> ProjectResponse:
    project = get_project(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Progetto non trovato.")

    return ProjectResponse(**project)


@app.get("/v1/workspace/projects/{project_id}/processes")
def get_workspace_project_processes(project_id: str) -> list[ProjectProcessResponse]:
    return [ProjectProcessResponse(**process) for process in list_project_processes(project_id)]


@app.post("/v1/workspace/projects/{project_id}/processes")
def create_workspace_process(
    project_id: str,
    request: CreateProcessRequest,
) -> ProjectProcessResponse:
    try:
        return ProjectProcessResponse(**create_process(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/workspace/projects/{project_id}/sources")
def get_workspace_project_sources(project_id: str) -> list[ProjectSourceResponse]:
    return [ProjectSourceResponse(**source) for source in list_project_sources(project_id)]


@app.post("/v1/workspace/projects/{project_id}/sources")
def create_workspace_project_source(
    project_id: str,
    request: CreateProjectSourceRequest,
) -> ProjectSourceResponse:
    try:
        return ProjectSourceResponse(**create_project_source(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/workspace/projects/{project_id}/decisions")
def get_workspace_project_decisions(project_id: str) -> list[ProjectDecisionResponse]:
    return [ProjectDecisionResponse(**decision) for decision in list_project_decisions(project_id)]


@app.post("/v1/workspace/projects/{project_id}/decisions")
def create_workspace_project_decision(
    project_id: str,
    request: CreateProjectDecisionRequest,
) -> ProjectDecisionResponse:
    try:
        return ProjectDecisionResponse(**create_project_decision(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/workspace/processes/{process_id}")
def get_workspace_process(process_id: str) -> ProjectProcessResponse:
    process = get_process(process_id)

    if process is None:
        raise HTTPException(status_code=404, detail="Processo non trovato.")

    return ProjectProcessResponse(**process)


@app.get("/v1/workspace/bpmn-models/{bpmn_model_id}")
def get_workspace_bpmn_model(bpmn_model_id: str) -> BpmnModelResponse:
    model = get_bpmn_model(bpmn_model_id)

    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    return BpmnModelResponse(**model)


@app.put("/v1/workspace/bpmn-models/{bpmn_model_id}")
def update_workspace_bpmn_model(
    bpmn_model_id: str,
    request: UpdateBpmnModelRequest,
) -> BpmnModelResponse:
    try:
        model = update_bpmn_model(bpmn_model_id, request.xml)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    return BpmnModelResponse(**model)


@app.get("/v1/workspace/bpmn-models/{bpmn_model_id}/versions")
def get_workspace_bpmn_versions(bpmn_model_id: str) -> list[BpmnVersionResponse]:
    return [BpmnVersionResponse(**version) for version in list_bpmn_versions(bpmn_model_id)]


@app.post("/v1/workspace/bpmn-models/{bpmn_model_id}/versions/{version_id}/restore")
def restore_workspace_bpmn_version(
    bpmn_model_id: str,
    version_id: int,
) -> RestoreBpmnVersionResponse:
    try:
        result = restore_bpmn_version(bpmn_model_id=bpmn_model_id, version_id=version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RestoreBpmnVersionResponse(**result)


@app.get("/v1/workspace/bpmn-models/{bpmn_model_id}/review")
def get_workspace_bpmn_review(bpmn_model_id: str) -> BpmnReviewResponse | None:
    review = get_bpmn_review(bpmn_model_id)

    if review is None:
        return None

    return BpmnReviewResponse(**review)


@app.post("/v1/workspace/bpmn-models/{bpmn_model_id}/review/approve")
def approve_workspace_bpmn_review(bpmn_model_id: str) -> ApproveBpmnReviewResponse:
    try:
        result = approve_bpmn_review(bpmn_model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApproveBpmnReviewResponse(**result)


@app.delete("/v1/workspace")
def clear_workspace():
    reset_workspace()
    return {"status": "ok"}


@app.post("/v1/consultant-chat/sessions/{thread_id}/messages")
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


@app.post("/v1/consultant-chat/sessions/{thread_id}/messages/stream")
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

        try:
            yield ndjson_event("start", thread_id=thread_id)

            if direct_response is not None:
                append_chat_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=direct_response,
                    model_name=request.model_name,
                )
                yield ndjson_event("delta", content=direct_response)
                yield ndjson_event("done", thread_id=thread_id, message=direct_response)
                return

            for delta in stream_agent_deltas(
                thread_id=thread_id,
                model_name=request.model_name,
                messages=[{"role": "user", "content": request.message}],
                scope=request.scope,
            ):
                response_parts.append(delta)
                yield ndjson_event("delta", content=delta)

            response_message = "".join(response_parts)
            append_chat_message(
                thread_id=thread_id,
                role="assistant",
                content=response_message,
                model_name=request.model_name,
            )
            yield ndjson_event("done", thread_id=thread_id, message=response_message)
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


@app.post("/v1/memory/save")
def save_memory(request: SaveMemoryRequest):
    result = save_consultant_memory(
        content=request.content,
        category=request.category,
    )

    return {
        "result": result,
    }


@app.post("/v1/memory/search")
def search_memory(request: SearchMemoryRequest):
    result = search_consultant_memory(
        query=request.query,
        category=request.category,
    )

    return {
        "result": result,
    }
