import asyncio
import json
import logging
from io import BytesIO
from typing import Any

import websockets
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI

from backend.schemas.chat_api import TranscriptionResponse
from backend.security import AuthPrincipal, authenticate_websocket, require_principal
from backend.services.transcription import (
    build_live_transcription_options,
    build_live_turn_detection,
    build_transcription_options,
    enforce_language,
    filter_live_transcript,
    normalize_language,
    resolve_keywords,
)
from backend.settings import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audio", tags=["audio"])

MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024

_transcription_client: AsyncOpenAI | None = None
_transcription_client_key: str | None = None


def transcription_client() -> AsyncOpenAI:
    """One async client for the whole process.

    Two reasons this is not built per request. The sync `OpenAI` client blocks
    the event loop for the entire upload and decode --- minutes, on a 25 MB
    interview --- which stalls every other request the app is serving. And a
    fresh client per request throws away the connection pool and carries no
    timeout, so a hung call hangs until the socket gives up.
    """
    global _transcription_client, _transcription_client_key

    api_key = settings.openai_api_key or ""

    if _transcription_client is None or _transcription_client_key != api_key:
        _transcription_client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.openai_transcription_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        _transcription_client_key = api_key

    return _transcription_client


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


@router.post("/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    _principal: AuthPrincipal = Depends(require_principal),
) -> TranscriptionResponse:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY non configurata.")

    try:
        target_language = normalize_language(language, settings.openai_transcription_language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="File audio vuoto.")

    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File audio troppo grande.")

    filename = file.filename or "audio.webm"
    content_type = file.content_type or "application/octet-stream"
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename

    transcription_options = build_transcription_options(
        model=settings.openai_transcription_model,
        language=target_language,
        keywords=resolve_keywords(settings.openai_transcription_keywords),
        temperature=settings.openai_transcription_temperature,
    )

    try:
        transcription = await transcription_client().audio.transcriptions.create(
            file=(filename, audio_file, content_type),
            **transcription_options,
        )
    except Exception as exc:
        # The upstream message can carry request and organization identifiers.
        # It belongs in the log, not in a response body.
        logger.exception("transcription request failed (model=%s)", settings.openai_transcription_model)
        raise HTTPException(status_code=502, detail="Trascrizione non riuscita.") from exc

    payload = openai_object_to_dict(transcription)
    raw_segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    guarded = enforce_language(
        language=target_language,
        segments=raw_segments,
        text=str(payload.get("text") or ""),
    )

    return TranscriptionResponse(
        text=format_diarized_transcript({"segments": guarded.segments, "text": guarded.text}),
        model=settings.openai_transcription_model,
        language=target_language,
        segments=guarded.segments,
        dropped_segments=guarded.dropped_segments,
        duration=payload.get("duration") if isinstance(payload.get("duration"), (float, int)) else None,
    )


@router.websocket("/live-transcription")
async def live_audio_transcription(websocket: WebSocket):
    principal = await authenticate_websocket(websocket)
    if principal is None:
        return

    await websocket.accept()

    if not settings.openai_api_key:
        await send_ws_event(websocket, "error", detail="OPENAI_API_KEY non configurata.")
        await websocket.close(code=1011)
        return

    openai_url = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
    }
    target_language = normalize_language(None, settings.openai_transcription_language)
    live_transcription_options = build_live_transcription_options(
        model=settings.openai_live_transcription_model,
        language=target_language,
        keywords=resolve_keywords(settings.openai_transcription_keywords),
    )
    turn_detection = build_live_turn_detection(
        silence_duration_ms=settings.openai_live_vad_silence_ms,
        prefix_padding_ms=settings.openai_live_vad_prefix_padding_ms,
        threshold=settings.openai_live_vad_threshold,
    )

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
                                    "transcription": live_transcription_options,
                                    "turn_detection": turn_detection,
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
                language=target_language,
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
                    elif event_type == "close":
                        # No manual commit: the API rejects one while server VAD
                        # owns the buffer. The last utterance is closed by the
                        # silence that follows it, and the diarized REST pass is
                        # the transcript of record either way.
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
                        # An item that came back in the wrong script is forwarded
                        # empty rather than swallowed, so the client still drops
                        # the provisional deltas it accumulated for that item.
                        transcript = str(event.get("transcript") or "")
                        kept = filter_live_transcript(transcript, target_language)
                        await send_ws_event(
                            websocket,
                            "completed",
                            transcript=kept,
                            filtered=bool(transcript) and not kept,
                            item_id=event.get("item_id"),
                        )
                    elif event_type in {
                        "conversation.item.input_audio_transcription.failed",
                        "error",
                    }:
                        # Upstream messages can carry request and organization
                        # identifiers, so they go to the log and the consultant
                        # gets a message they can act on.
                        logger.warning("live transcription upstream error: %s", event.get("error"))
                        await send_ws_event(
                            websocket,
                            "error",
                            detail="Trascrizione live non riuscita.",
                        )

            client_task = asyncio.create_task(forward_client_audio())
            openai_task = asyncio.create_task(forward_openai_events())
            done, pending = await asyncio.wait(
                {client_task, openai_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            await asyncio.gather(*pending, return_exceptions=True)

            for task in done:
                exception = task.exception()
                if exception and not isinstance(exception, WebSocketDisconnect):
                    raise exception
    except websockets.exceptions.ConnectionClosed:
        logger.warning("live transcription: OpenAI Realtime closed the connection", exc_info=True)
        try:
            await send_ws_event(
                websocket,
                "error",
                detail="Connessione a OpenAI Realtime interrotta.",
            )
        except Exception:
            pass
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("live transcription session failed")
        try:
            await send_ws_event(websocket, "error", detail="Trascrizione live non riuscita.")
        except Exception:
            pass
