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

from backend.agent import get_agent
from backend.database import (
    append_chat_message,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
)
from backend.memory.semantic.semantic_store import (
    save_consultant_memory,
    search_consultant_memory,
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


def stream_agent_deltas(thread_id: str, model_name: str | None, messages: list[dict]) -> Iterator[str]:
    agent = get_agent(model_name)
    thread_lock = get_thread_lock(thread_id)

    with thread_lock:
        events = agent.stream(
            {
                "messages": messages
            },
            config={
                "configurable": {
                    "thread_id": thread_id,
                }
            },
            stream_mode="messages",
        )

        for event in events:
            if isinstance(event, tuple):
                chunk, metadata = event
            else:
                chunk, metadata = event, {}

            if metadata.get("langgraph_node") != "chatbot":
                continue

            if getattr(chunk, "type", None) not in {"AIMessageChunk", "ai"}:
                continue

            content = message_content_to_text(getattr(chunk, "content", ""))

            if content:
                yield content


def stream_agent_text(thread_id: str, model_name: str | None, messages: list[dict]) -> str:
    return "".join(stream_agent_deltas(thread_id, model_name, messages))


def ndjson_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]  # List of messages, each message is a dict with 'role' and 'content'
    thread_id: str


class CreateSessionRequest(BaseModel):
    model_name: str | None = None
    title: str | None = None


class CreateSessionResponse(BaseModel):
    thread_id: str
    model_name: str | None = None
    title: str = "Nuova chat"


class ChatMessageRecord(BaseModel):
    id: int | None = None
    role: str
    content: str
    created_at: str | None = None


class ChatSessionSummary(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatSessionDetail(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    created_at: str
    updated_at: str
    messages: list[ChatMessageRecord]


class SendMessageRequest(BaseModel):
    message: str
    model_name: str | None = None


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
    return FileResponse(FRONTEND_INDEX)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        response_message = stream_agent_text(
            thread_id=request.thread_id,
            model_name=request.model_name,
            messages=request.messages,
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

    openai_url = f"wss://api.openai.com/v1/realtime?model={settings.openai_live_transcription_model}"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
    }

    try:
        async with websockets.connect(
            openai_url,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
        ) as openai_ws:
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
                    elif event_type == "commit":
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    elif event_type == "close":
                        await openai_ws.close()
                        break

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
                    elif event_type == "error":
                        error = event.get("error") or {}
                        await send_ws_event(
                            websocket,
                            "error",
                            detail=error.get("message") or "Errore OpenAI Realtime.",
                        )

            client_task = asyncio.create_task(forward_client_audio())
            openai_task = asyncio.create_task(forward_openai_events())
            done, pending = await asyncio.wait(
                {client_task, openai_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            for task in done:
                exception = task.exception()
                if exception:
                    raise exception
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
    session = create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
        title=request.title or "Nuova chat",
    )

    return CreateSessionResponse(
        thread_id=session["thread_id"],
        model_name=session["model_name"],
        title=session["title"],
    )


@app.get("/v1/consultant-chat/sessions")
def get_consultant_chat_sessions() -> list[ChatSessionSummary]:
    return [ChatSessionSummary(**session) for session in list_chat_sessions()]


@app.get("/v1/consultant-chat/sessions/{thread_id}")
def get_consultant_chat_session(thread_id: str) -> ChatSessionDetail:
    session = get_chat_session(thread_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")

    return ChatSessionDetail(**session)


@app.delete("/v1/consultant-chat/sessions")
def clear_consultant_chat_sessions():
    delete_all_chat_sessions()
    return {"status": "ok"}


@app.delete("/v1/consultant-chat/sessions/{thread_id}")
def remove_consultant_chat_session(thread_id: str):
    delete_chat_session(thread_id)
    return {"status": "ok"}


@app.post("/v1/consultant-chat/sessions/{thread_id}/messages")
def send_consultant_chat_message(
    thread_id: str,
    request: SendMessageRequest,
) -> ChatResponse:
    create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
    )
    append_chat_message(
        thread_id=thread_id,
        role="user",
        content=request.message,
        model_name=request.model_name,
    )

    try:
        response_message = stream_agent_text(
            thread_id=thread_id,
            model_name=request.model_name,
            messages=[
                {"role": "user", "content": request.message},
            ],
        )
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
    create_chat_session(
        thread_id=thread_id,
        model_name=request.model_name,
    )
    append_chat_message(
        thread_id=thread_id,
        role="user",
        content=request.message,
        model_name=request.model_name,
    )

    def generate():
        response_parts = []

        try:
            yield ndjson_event("start", thread_id=thread_id)

            for delta in stream_agent_deltas(
                thread_id=thread_id,
                model_name=request.model_name,
                messages=[
                    {"role": "user", "content": request.message},
                ],
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
