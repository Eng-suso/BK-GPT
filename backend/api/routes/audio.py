import asyncio
import json
import logging
from io import BytesIO
from typing import Any

import websockets
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from backend.llm import LlmTask, OperationKind, Outcome, operation, profile_for, transcribe
from backend.llm.usage import record, update_audio_seconds
from backend.schemas.chat_api import TranscriptionResponse
from backend.llm.egress import Destination, EgressBlocked, require
from backend.llm.budget import UsageLimitReached, check_audio, follows_live_recording, remaining_audio_seconds
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

def openai_object_to_dict(value: Any) -> dict[str, Any]:
    """Convert a supported response object or mapping to a dictionary.
    
    Args:
        value (Any): Untrusted value to convert.
    
    Returns:
        dict[str, Any]: The converted dictionary, or an empty dictionary when the
            value cannot be converted.
    """
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
    principal: AuthPrincipal = Depends(require_principal),
) -> TranscriptionResponse:
    """
    Transcribe an uploaded audio file and return a language-filtered transcript.
    
    The audio upload and requested language are treated as untrusted input. The function
    rejects missing API configuration, invalid language values, empty files, oversized
    files, and upstream transcription failures. It does not persist the uploaded audio
    or transcription.
    
    Args:
        file (UploadFile): Untrusted audio file to transcribe.
        language (str | None): Untrusted requested language, or the configured default
            when omitted.
    
    Returns:
        TranscriptionResponse: The formatted transcript, language, model, accepted
            segments, dropped segments, and optional duration.
    
    Raises:
        HTTPException: With status 503 when the OpenAI API key is unavailable, 422 for
            an invalid language, 400 for an empty file, 413 for an oversized file, or
            502 when the upstream transcription service fails.
    """
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY non configurata.")

    # La seconda passata di una registrazione dal vivo (la trascrizione con i
    # nomi) e' lo stesso audio gia' contato: non consuma ore e non si rifiuta,
    # perche' una registrazione iniziata arriva in fondo. Un file caricato a se'
    # guarda il tetto delle ore come ogni nuova registrazione.
    after_live = await asyncio.to_thread(
        follows_live_recording, principal.user_id, tenant_id=principal.tenant_id
    )
    if not after_live:
        await asyncio.to_thread(check_audio, principal.user_id, tenant_id=principal.tenant_id)

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

    # Il modello si chiede al profilo del compito, non ai settings: e' la stessa
    # fonte che il gateway usera' per eseguire. Le opzioni dipendono dal modello
    # - `response_format`, `chunking_strategy`, `keywords` escono da
    # `capabilities_for` - quindi due letture separate potrebbero costruire le
    # opzioni per un modello ed eseguirne un altro: chiederebbe la diarizzazione
    # a un modello che non la fa, e la trascrizione tornerebbe senza speaker.
    transcription_options = build_transcription_options(
        model=profile_for(LlmTask.TRANSCRIPTION).model,
        language=target_language,
        keywords=resolve_keywords(settings.openai_transcription_keywords),
        temperature=settings.openai_transcription_temperature,
    )

    try:
        # Caricare un audio e' un lavoro, quindi un'operazione: senza, il
        # gateway rifiuta e le ore di audio tornerebbero a essere spesa senza
        # nome - e sono la voce che cresce piu' in fretta quando il consulente
        # registra le interviste.
        kind = OperationKind.TRANSCRIPTION_AFTER_LIVE if after_live else OperationKind.TRANSCRIPTION
        with operation(kind):
            transcription = await transcribe(
                file=(filename, audio_file, content_type),
                options=transcription_options,
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


#: L'audio dal vivo arriva come PCM a 16 bit, mono, a 24 kHz (vedi `session.update`).
_PCM_BYTES_PER_SECOND = 24_000 * 2


class LiveAudioMeter:
    """Conta i secondi di audio mandati al fornitore: e' cio' che si paga.

    Dai byte e non dall'orologio: una registrazione in pausa non costa, e un
    secondo di audio mandato costa anche se la sessione cade subito dopo.
    """

    def __init__(self) -> None:
        self._bytes = 0
        # Il tetto di questa registrazione (secondi), o `None`; e la sua riga.
        self.cap_seconds: int | None = None
        self.ledger: "LiveSessionLedger | None" = None

    @property
    def over_cap(self) -> bool:
        return self.cap_seconds is not None and self.seconds >= self.cap_seconds

    def add(self, audio_base64: str) -> None:
        # La lunghezza decodificata di un base64, senza decodificarlo.
        padding = audio_base64[-2:].count("=")
        self._bytes += max(0, len(audio_base64) * 3 // 4 - padding)

    @property
    def seconds(self) -> int:
        return round(self._bytes / _PCM_BYTES_PER_SECOND)


#: Ogni quanto la riga della registrazione si aggiorna mentre si registra.
_FLUSH_EVERY_SECONDS = 30
#: Quanto si puo' registrare oltre il tetto delle ore: un'intervista non si
#: tronca sull'ultima frase, ma neanche si lascia andare per ore.
_GRACE_SECONDS = 600
#: Le registrazioni aperte in questo processo, una per consulente.
_ACTIVE_RECORDINGS: set[tuple[str, str]] = set()


class LiveSessionLedger:
    """La riga di una registrazione dal vivo nel registro dei consumi.

    Il WebSocket va diretto a OpenAI Realtime e non passa dal gateway. La riga
    si apre all'inizio e si aggiorna ogni `_FLUSH_EVERY_SECONDS`: un riavvio del
    server non perde i minuti gia' pagati, il pannello li vede mentre si
    registra, e la seconda passata del file trova la riga gia' scritta.
    """

    def __init__(self, principal: AuthPrincipal) -> None:
        self._principal = principal
        self._row_id: str | None = None
        self._flushed = 0

    def open(self) -> None:
        with operation(
            OperationKind.TRANSCRIPTION, tenant_id=self._principal.tenant_id, user_id=self._principal.user_id
        ) as opened:
            self._row_id = record(
                operation=opened,
                task=LlmTask.LIVE_TRANSCRIPTION.value,
                model=profile_for(LlmTask.LIVE_TRANSCRIPTION).model,
                outcome=Outcome.OK,
            )

    def due(self, seconds: int) -> bool:
        return seconds - self._flushed >= _FLUSH_EVERY_SECONDS

    def flush(self, seconds: int) -> None:
        update_audio_seconds(self._row_id, seconds)
        self._flushed = seconds


@router.websocket("/live-transcription")
async def live_audio_transcription(websocket: WebSocket):
    """Manage an authenticated live audio transcription session over a WebSocket.
    
    The session forwards client audio as 24 kHz PCM to OpenAI Realtime using
    server-side voice activity detection, relays transcription events, and filters
    completed transcripts to the configured language. Authentication, missing API
    configuration, upstream connection failures, malformed client messages, and
    client disconnections are handled through safe WebSocket responses or session
    termination. Client messages are treated as untrusted input.
    
    Args:
        websocket (WebSocket): Untrusted client WebSocket used for authentication,
            audio events, and transcription responses.
    
    Side Effects:
        Accepts and communicates over the client WebSocket, opens an upstream
        OpenAI Realtime connection, and logs upstream or session failures. Does not
        persist audio or transcripts.
    """
    principal = await authenticate_websocket(websocket)
    if principal is None:
        return

    # Il tetto delle ore di audio si guarda all'apertura, mai a meta': una
    # registrazione iniziata arriva in fondo.
    try:
        await asyncio.to_thread(check_audio, principal.user_id, tenant_id=principal.tenant_id)
    except UsageLimitReached as exc:
        await send_ws_event(websocket, "error", detail=str(exc), code="usage_limit_reached")
        await websocket.close(code=1008)
        return
    recording_key = (principal.tenant_id, principal.user_id)
    if recording_key in _ACTIVE_RECORDINGS:
        # Una alla volta: piu' schede che registrano insieme passerebbero tutte
        # il controllo all'apertura con lo stesso budget.
        await send_ws_event(
            websocket, "error", code="usage_limit_reached",
            detail="Hai gia' una registrazione in corso. Chiudi quella prima di iniziarne un'altra.",
        )
        await websocket.close(code=1008)
        return
    remaining = await asyncio.to_thread(
        remaining_audio_seconds, principal.user_id, tenant_id=principal.tenant_id
    )
    meter = LiveAudioMeter()
    meter.cap_seconds = None if remaining is None else remaining + _GRACE_SECONDS

    if not settings.openai_api_key:
        await send_ws_event(websocket, "error", detail="OPENAI_API_KEY non configurata.")
        await websocket.close(code=1011)
        return

    try:
        openai_url = require(Destination.TRANSCRIPTION_LIVE).url
    except EgressBlocked as exc:
        await send_ws_event(websocket, "error", detail=str(exc))
        await websocket.close(code=1011)
        return
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

    ledger = LiveSessionLedger(principal)
    await asyncio.to_thread(ledger.open)
    meter.ledger = ledger
    _ACTIVE_RECORDINGS.add(recording_key)
    try:
        await _live_session(websocket, meter, openai_url, headers, target_language,
                            live_transcription_options, turn_detection)
    finally:
        _ACTIVE_RECORDINGS.discard(recording_key)
        # L'ultimo aggiornamento, anche se e' finita male: i secondi mandati a
        # OpenAI si pagano comunque.
        await asyncio.to_thread(ledger.flush, meter.seconds)


async def _live_session(
    websocket: WebSocket,
    meter: LiveAudioMeter,
    openai_url: str,
    headers: dict[str, str],
    target_language: str,
    live_transcription_options: dict,
    turn_detection: dict,
) -> None:
    """La sessione col fornitore: inoltra l'audio e rimanda le trascrizioni."""
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
                """Forward client audio events to the upstream transcription connection.
                
                Treats received WebSocket messages as untrusted input. Audio payloads are forwarded
                to the upstream service, and a close event closes that connection. This function
                does not persist audio or transcripts.
                
                Side Effects:
                    Sends audio events to and closes the upstream WebSocket connection.
                """
                while True:
                    message = await websocket.receive_text()
                    event = json.loads(message)
                    event_type = event.get("type")

                    if event_type == "audio":
                        audio = event.get("audio")
                        if audio:
                            meter.add(audio)
                            if meter.ledger is not None and meter.ledger.due(meter.seconds):
                                await asyncio.to_thread(meter.ledger.flush, meter.seconds)
                            if meter.over_cap:
                                # Il tetto e' arrivato a meta': si chiude come un
                                # arresto normale e il file parte per i nomi.
                                await send_ws_event(
                                    websocket, "error", code="usage_limit_cut",
                                    detail="Hai raggiunto le ore di registrazione: la registrazione si chiude qui.",
                                )
                                await openai_ws.close()
                                break
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
                """Relay transcription events from the upstream WebSocket to the client.
                
                Filters completed transcripts to the target language and preserves item completion
                events with an empty transcript when all text is filtered. Sends transcription
                deltas, completion notifications, and generic error events to the client while
                logging upstream error details. Performs WebSocket I/O and does not persist data.
                """
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
