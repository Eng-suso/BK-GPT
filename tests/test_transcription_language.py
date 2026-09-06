"""The language lock and the vocabulary bias, per model.

These guard two field failures: Italian interviews coming back with Bengali and
Korean segments spliced in, and silences filled with invented English. Both
fixes are per-model, because the API rejects `prompt` on the diarize model and
reads `keywords` on only some models --- so the assertions below are as much
about what we do NOT send as about what we do.
"""
import pytest
from fastapi.testclient import TestClient

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
    """The REST route with a recording stub in place of the OpenAI client."""
    from backend.api.routes import audio
    from backend.app import app
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

    with TestClient(app) as client:
        yield client, calls


def _post_audio(client: TestClient, **data):
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


def test_route_does_not_leak_the_upstream_error_to_the_caller(monkeypatch, transcription_client):
    """Upstream messages carry request and organization identifiers."""
    from backend.api.routes import audio

    class FailingClient:
        class audio:  # noqa: N801 - mirrors the SDK's attribute layout
            class transcriptions:
                @staticmethod
                async def create(**_options):
                    raise RuntimeError("rate limit for org-SECRET123 request req-abc")

    client, _calls = transcription_client
    monkeypatch.setattr(audio, "transcription_client", lambda: FailingClient())

    response = _post_audio(client)

    assert response.status_code == 502
    assert "SECRET123" not in response.text
    assert response.json()["error"]["message"] == "Trascrizione non riuscita."


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
