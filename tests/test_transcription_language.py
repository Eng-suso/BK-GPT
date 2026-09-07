"""The language lock and the vocabulary bias, per model.

These guard two field failures: Italian interviews coming back with Bengali and
Korean segments spliced in, and silences filled with invented English. Both
fixes are per-model, because the API rejects `prompt` on the diarize model and
reads `keywords` on only some models --- so the assertions below are as much
about what we do NOT send as about what we do.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.services.transcription import (
    DEFAULT_KEYWORDS,
    MIN_LETTERS_FOR_SCRIPT_CHECK,
    build_live_transcription_options,
    build_live_turn_detection,
    build_transcription_options,
    capabilities_for,
    enforce_language,
    filter_live_transcript,
    is_off_script,
    normalize_language,
    resolve_keywords,
)


# --- capability table ------------------------------------------------------


def test_diarize_model_never_gets_prompt_or_keywords():
    """The API rejects both on `gpt-4o-transcribe-diarize`; sending them 400s."""
    options = build_transcription_options(
        model="gpt-4o-transcribe-diarize",
        language="it",
        keywords=["BPMN"],
        temperature=0.0,
    )

    assert "prompt" not in options
    assert "keywords" not in options
    assert options["language"] == "it"
    assert options["response_format"] == "diarized_json"
    assert options["chunking_strategy"] == "auto"
    assert options["temperature"] == 0.0


def test_prompt_capable_model_gets_a_prompt_in_the_target_language():
    options = build_transcription_options(
        model="gpt-4o-transcribe",
        language="it",
        keywords=["BPMN"],
        temperature=0.0,
    )

    assert "BPMN" in options["prompt"]
    assert "italiano" in options["prompt"]
    # `keywords` is a `gpt-transcribe` field only.
    assert "keywords" not in options
    assert "response_format" not in options


def test_keyword_capable_model_gets_the_glossary():
    options = build_transcription_options(
        model="gpt-transcribe",
        language="it",
        keywords=["BPMN", "handoff"],
    )

    assert options["keywords"] == ["BPMN", "handoff"]


def test_unknown_model_gets_language_only():
    """A model we have no spec for must not be probed with guessed params."""
    options = build_transcription_options(
        model="some-future-model",
        language="it",
        keywords=["BPMN"],
        temperature=0.0,
    )

    assert options == {"model": "some-future-model", "language": "it"}


def test_live_options_lock_language_without_unsupported_prompt():
    options = build_live_transcription_options(
        model="gpt-realtime-whisper",
        language="it",
        keywords=["BPMN"],
    )

    assert options == {"model": "gpt-realtime-whisper", "language": "it"}


def test_live_keyword_capable_model_gets_the_glossary():
    options = build_live_transcription_options(
        model="gpt-live-transcribe",
        language="it",
        keywords=["BPMN"],
    )

    assert options["keywords"] == ["BPMN"]


def test_prompt_is_skipped_for_a_language_we_cannot_phrase_it_in():
    """An English prompt over German audio pulls the transcript off-language."""
    options = build_transcription_options(model="gpt-4o-transcribe", language="de", keywords=["BPMN"])

    assert "prompt" not in options


def test_capabilities_are_looked_up_after_stripping():
    assert capabilities_for(" whisper-1 ").supports_prompt is True


# --- language normalization ------------------------------------------------


def test_language_falls_back_to_the_configured_default():
    assert normalize_language(None, "it") == "it"
    assert normalize_language("  ", "it") == "it"


def test_language_is_normalized_to_lowercase_iso_639_1():
    assert normalize_language("IT", "en") == "it"


@pytest.mark.parametrize("bad", ["italiano", "it-IT", "i", "123"])
def test_malformed_language_is_rejected_not_silently_dropped(bad: str):
    with pytest.raises(ValueError):
        normalize_language(bad, "it")


# --- script guard ----------------------------------------------------------


def test_off_script_detects_a_segment_in_another_alphabet():
    assert is_off_script("আলো আমি vorrei valutare", "LATIN") is False  # mostly latin
    assert is_off_script("আলো আমি বলছি এখন কিছু", "LATIN") is True
    assert is_off_script("맞아 그렇게 하겠습니다", "LATIN") is True


def test_accented_italian_is_not_off_script():
    assert is_off_script("L'attività è già stata assegnata al responsabile", "LATIN") is False


def test_short_text_is_never_judged():
    """Too few letters to tell an interjection from a language switch."""
    short = "맞아"
    assert len(short) < MIN_LETTERS_FOR_SCRIPT_CHECK
    assert is_off_script(short, "LATIN") is False


def test_guard_drops_only_the_off_script_segments():
    result = enforce_language(
        language="it",
        segments=[
            {"speaker": "A", "text": "Vorrei capire come vengono fatte queste valutazioni"},
            {"speaker": "A", "text": "আলো আমি বলছি এখন কিছু"},
            {"speaker": "B", "text": "Il processo passa dal responsabile di funzione"},
        ],
        text="",
    )

    assert result.dropped_segments == 1
    assert [segment["speaker"] for segment in result.segments] == ["A", "B"]
    assert all("আ" not in segment["text"] for segment in result.segments)


def test_guard_filters_line_by_line_when_the_model_returned_no_segments():
    result = enforce_language(
        language="it",
        segments=[],
        text="Vorrei valutare come lavorate\n맞아 그렇게 하겠습니다\nIl processo parte dal cliente",
    )

    assert result.dropped_segments == 1
    assert result.text == "Vorrei valutare come lavorate\nIl processo parte dal cliente"


def test_guard_does_not_double_count_segments_and_fallback_text():
    """`text` is only read when there are no segments, so it must not be tallied."""
    result = enforce_language(
        language="it",
        segments=[{"speaker": "A", "text": "আলো আমি বলছি এখন কিছু"}],
        text="আলো আমি বলছি এখন কিছু",
    )

    assert result.dropped_segments == 1


def test_guard_is_a_passthrough_for_a_language_we_have_no_script_for():
    """Better a wrong-language transcript than a deleted correct one."""
    segments = [{"speaker": "A", "text": "맞아 그렇게 하겠습니다"}]
    result = enforce_language(language="ko", segments=segments, text="")

    assert result.segments == segments
    assert result.dropped_segments == 0


def test_live_filter_empties_an_off_script_item():
    assert filter_live_transcript("আলো আমি বলছি এখন কিছু", "it") == ""
    assert filter_live_transcript("Il processo parte dal cliente", "it") != ""


# --- glossary --------------------------------------------------------------


def test_deployment_keywords_extend_the_built_in_glossary_without_duplicates():
    keywords = resolve_keywords("Fatturazione, BPMN ,  ")

    assert keywords[: len(DEFAULT_KEYWORDS)] == list(DEFAULT_KEYWORDS)
    assert keywords.count("BPMN") == 1
    assert keywords[-1] == "Fatturazione"


# --- the route actually wires both of the above ----------------------------


@pytest.fixture()
def transcription_client(monkeypatch):
    """Provide a test client and recorded transcription options for REST route tests.
    
    Yields:
        tuple: The test client and a list populated with transcription request options.
    """
    from backend.api.routes import audio
    from backend.settings import settings

    calls: list[dict] = []

    class StubTranscriptions:
        async def create(self, **options):
            calls.append(options)
            return {
                "text": "",
                "duration": 12.5,
                "segments": [
                    {"speaker": "A", "text": "Vorrei capire come lavorate su questo processo"},
                    {"speaker": "A", "text": "আলো আমি বলছি এখন কিছু"},
                ],
            }

    class StubClient:
        audio = type("Audio", (), {"transcriptions": StubTranscriptions()})()

    monkeypatch.setattr(audio, "transcription_client", lambda: StubClient())
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_transcription_model", "gpt-4o-transcribe-diarize")
    monkeypatch.setattr(settings, "openai_transcription_language", "it")

    test_app = FastAPI()
    test_app.include_router(audio.router)

    with TestClient(test_app) as client:
        yield client, calls


def _post_audio(client: TestClient, **data):
    """Submit fake audio data to the transcription endpoint for testing.
    
    Parameters:
    	client (TestClient): Client used to make the HTTP request
    	**data: Form fields included in the request
    
    Returns:
    	The endpoint response.
    """
    return client.post(
        "/v1/audio/transcriptions",
        files={"file": ("intervista.webm", b"fake-audio-bytes", "audio/webm")},
        data=data or None,
    )


def test_route_locks_the_language_and_drops_the_off_script_segment(transcription_client):
    client, calls = transcription_client

    response = _post_audio(client)

    assert response.status_code == 200
    assert calls[0]["language"] == "it"
    assert "prompt" not in calls[0]

    body = response.json()
    assert body["language"] == "it"
    assert body["dropped_segments"] == 1
    assert len(body["segments"]) == 1
    assert body["text"] == "A: Vorrei capire come lavorate su questo processo"
    assert body["duration"] == 12.5


def test_route_rejects_a_malformed_language_before_calling_the_api(transcription_client):
    client, calls = transcription_client

    response = _post_audio(client, language="italiano")

    assert response.status_code == 422
    assert calls == []


def test_route_honors_a_normalized_language_override(transcription_client):
    client, calls = transcription_client

    response = _post_audio(client, language=" EN ")

    assert response.status_code == 200
    assert calls[0]["language"] == "en"
    assert response.json()["language"] == "en"


def test_route_authentication_failure_never_reaches_transcription_service(
    monkeypatch,
    transcription_client,
):
    from backend.settings import settings

    client, calls = transcription_client
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "expected-token")

    response = _post_audio(client)

    assert response.status_code == 401
    assert calls == []


def test_route_does_not_leak_the_upstream_error_to_the_caller(monkeypatch, transcription_client):
    """Upstream messages carry request and organization identifiers."""
    from backend.api.routes import audio

    class FailingClient:
        class audio:  # noqa: N801 - mirrors the SDK's attribute layout
            class transcriptions:
                @staticmethod
                async def create(**_options):
                    """
                    Simulate an upstream rate-limit failure.
                    
                    Raises:
                    	RuntimeError: Always raised with a rate-limit error message.
                    """
                    raise RuntimeError("rate limit for org-SECRET123 request req-abc")

    client, _calls = transcription_client
    monkeypatch.setattr(audio, "transcription_client", lambda: FailingClient())

    response = _post_audio(client)

    assert response.status_code == 502
    assert "SECRET123" not in response.text
    assert response.json()["detail"] == "Trascrizione non riuscita."


def test_async_transcription_client_is_reused_until_the_api_key_changes(monkeypatch):
    """Client reuse preserves the connection pool; key rotation rebuilds it."""
    from backend.api.routes import audio
    from backend.settings import settings

    created = []

    class RecordingAsyncOpenAI:
        def __init__(self, **options):
            self.options = options
            created.append(self)

    monkeypatch.setattr(audio, "AsyncOpenAI", RecordingAsyncOpenAI)
    monkeypatch.setattr(audio, "_transcription_client", None)
    monkeypatch.setattr(audio, "_transcription_client_key", None)
    monkeypatch.setattr(settings, "openai_api_key", "first-key")
    monkeypatch.setattr(settings, "openai_transcription_timeout_seconds", 123.0)
    monkeypatch.setattr(settings, "model_max_retries", 4)

    first = audio.transcription_client()
    reused = audio.transcription_client()

    assert reused is first
    assert len(created) == 1
    assert first.options == {
        "api_key": "first-key",
        "timeout": 123.0,
        "max_retries": 4,
    }

    monkeypatch.setattr(settings, "openai_api_key", "rotated-key")
    rotated = audio.transcription_client()

    assert rotated is not first
    assert len(created) == 2
    assert rotated.options["api_key"] == "rotated-key"


# --- live turn detection ---------------------------------------------------


def test_server_vad_replaces_the_wall_clock_commit():
    turn_detection = build_live_turn_detection(
        silence_duration_ms=800,
        prefix_padding_ms=300,
        threshold=0.5,
    )

    assert turn_detection["type"] == "server_vad"
    # Above the API's own 500ms default: an interview pause is not a turn end.
    assert turn_detection["silence_duration_ms"] == 800
    assert turn_detection["prefix_padding_ms"] == 300
    assert turn_detection["threshold"] == 0.5


class _FakeOpenAIWebSocket:
    """A deterministic boundary double for the external Realtime socket."""

    def __init__(self, events=(), *, hold_open: bool = False):
        self.events = list(events)
        self.hold_open = hold_open
        self.sent: list[dict] = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def send(self, message: str):
        self.sent.append(json.loads(message))

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.events:
            return json.dumps(self.events.pop(0))
        if self.hold_open:
            await asyncio.Event().wait()
        raise StopAsyncIteration


def _live_client(monkeypatch, openai_ws: _FakeOpenAIWebSocket):
    from backend.api.routes import audio
    from backend.settings import settings

    connect_calls = []

    def connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return openai_ws

    monkeypatch.setattr(audio.websockets, "connect", connect)
    monkeypatch.setattr(settings, "delir_auth_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_transcription_language", "it")
    monkeypatch.setattr(settings, "openai_live_transcription_model", "gpt-realtime-whisper")
    monkeypatch.setattr(settings, "openai_live_vad_silence_ms", 875)
    monkeypatch.setattr(settings, "openai_live_vad_prefix_padding_ms", 325)
    monkeypatch.setattr(settings, "openai_live_vad_threshold", 0.65)

    test_app = FastAPI()
    test_app.include_router(audio.router)
    return TestClient(test_app), connect_calls


def test_live_session_wires_language_vad_and_filtered_completion(monkeypatch):
    openai_ws = _FakeOpenAIWebSocket(
        [
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "item-7",
                "transcript": "আলো আমি বলছি এখন কিছু",
            }
        ]
    )
    client, connect_calls = _live_client(monkeypatch, openai_ws)

    with client.websocket_connect("/v1/audio/live-transcription") as websocket:
        ready = websocket.receive_json()
        completed = websocket.receive_json()

    assert ready == {
        "type": "ready",
        "model": "gpt-realtime-whisper",
        "language": "it",
        "sample_rate": 24000,
    }
    assert completed == {
        "type": "completed",
        "transcript": "",
        "filtered": True,
        "item_id": "item-7",
    }

    assert len(connect_calls) == 1
    _args, kwargs = connect_calls[0]
    assert kwargs["additional_headers"] == {"Authorization": "Bearer test-key"}
    session_input = openai_ws.sent[0]["session"]["audio"]["input"]
    assert session_input["transcription"] == {
        "model": "gpt-realtime-whisper",
        "language": "it",
    }
    assert session_input["turn_detection"] == {
        "type": "server_vad",
        "silence_duration_ms": 875,
        "prefix_padding_ms": 325,
        "threshold": 0.65,
    }


@pytest.mark.parametrize(
    "upstream_event_type",
    ["conversation.item.input_audio_transcription.failed", "error"],
)
def test_live_upstream_failures_are_sanitized(monkeypatch, upstream_event_type: str):
    openai_ws = _FakeOpenAIWebSocket(
        [
            {
                "type": upstream_event_type,
                "error": {"message": "failure for org-SECRET123 request req-abc"},
            }
        ]
    )
    client, _connect_calls = _live_client(monkeypatch, openai_ws)

    with client.websocket_connect("/v1/audio/live-transcription") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        error = websocket.receive_json()

    assert error == {"type": "error", "detail": "Trascrizione live non riuscita."}
    assert "SECRET123" not in json.dumps(error)


def test_live_server_vad_ignores_manual_commit_and_closes_cleanly(monkeypatch):
    openai_ws = _FakeOpenAIWebSocket(hold_open=True)
    client, _connect_calls = _live_client(monkeypatch, openai_ws)

    with client.websocket_connect("/v1/audio/live-transcription") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "audio", "audio": "cGNt"})
        websocket.send_json({"type": "commit"})
        websocket.send_json({"type": "close"})

    assert [event["type"] for event in openai_ws.sent] == [
        "session.update",
        "input_audio_buffer.append",
    ]
    assert openai_ws.sent[1]["audio"] == "cGNt"
    assert openai_ws.closed is True


def test_live_websocket_requires_authentication_before_connecting_upstream(monkeypatch):
    from backend.settings import settings

    openai_ws = _FakeOpenAIWebSocket()
    client, connect_calls = _live_client(monkeypatch, openai_ws)
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "expected-token")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/v1/audio/live-transcription"):
            pass

    assert exc_info.value.code == 1008
    assert connect_calls == []
