"""Language lock and vocabulary bias for the two speech-to-text paths.

Field transcripts of Italian interviews came back with Bengali and Korean
segments spliced into them, plus whole English sentences nobody said. Two
distinct causes:

1. no language lock. `gpt-4o-transcribe-diarize` cuts the audio into chunks
   server-side and detects the language of each chunk independently, so one
   recording can drift language segment by segment.
2. no vocabulary bias, so low-energy audio gets filled in with plausible
   invented speech instead of nothing.

Neither fix is uniform across models: the API rejects `prompt` on the diarize
model and on `gpt-realtime-whisper`, and only some models read `keywords`. The
capability table below is transcribed from the SDK's own request types rather
than guessed --- `openai/types/audio/transcription_create_params.py` and
`openai/types/realtime/audio_transcription_param.py`, openai 2.53.0 --- and the
option builders send a knob only where the model accepts it. An unknown model
gets the conservative row: language only.

The language lock is enforced twice, because the API side of it is advisory:
`language` improves accuracy but does not stop a chunk from coming back in
another script. `enforce_language` drops what still arrives off-script, so the
consultant reads a transcript with a hole in it rather than one with confident
nonsense in it.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)

ISO_639_1 = re.compile(r"^[a-z]{2}$")


@dataclass(frozen=True)
class TranscriptionCapabilities:
    """Which bias knobs a given speech-to-text model accepts.

    `language` is deliberately absent: every model in the table accepts it, and
    a model that did not would need the guard below anyway.
    """

    supports_prompt: bool = False
    supports_keywords: bool = False
    supports_temperature: bool = False
    diarized: bool = False


# Conservative row for a model we have no spec for: send nothing but `language`.
UNKNOWN_MODEL_CAPABILITIES = TranscriptionCapabilities()

MODEL_CAPABILITIES: dict[str, TranscriptionCapabilities] = {
    # REST /v1/audio/transcriptions
    "gpt-4o-transcribe-diarize": TranscriptionCapabilities(
        supports_temperature=True,
        diarized=True,
    ),
    "gpt-transcribe": TranscriptionCapabilities(
        supports_prompt=True,
        supports_keywords=True,
        supports_temperature=True,
    ),
    "gpt-4o-transcribe": TranscriptionCapabilities(
        supports_prompt=True,
        supports_temperature=True,
    ),
    "gpt-4o-mini-transcribe": TranscriptionCapabilities(
        supports_prompt=True,
        supports_temperature=True,
    ),
    "gpt-4o-mini-transcribe-2025-12-15": TranscriptionCapabilities(
        supports_prompt=True,
        supports_temperature=True,
    ),
    "whisper-1": TranscriptionCapabilities(
        supports_prompt=True,
        supports_temperature=True,
    ),
    # Realtime transcription sessions. `temperature` is not a field of the
    # realtime transcription config, so it stays False here.
    "gpt-live-transcribe": TranscriptionCapabilities(supports_keywords=True),
    # The SDK states prompt is not supported with this model in GA sessions.
    "gpt-realtime-whisper": TranscriptionCapabilities(),
}


def capabilities_for(model: str) -> TranscriptionCapabilities:
    return MODEL_CAPABILITIES.get(model.strip(), UNKNOWN_MODEL_CAPABILITIES)


# --- vocabulary bias -------------------------------------------------------

# The words a DeliR interview actually turns on. Kept short on purpose: a long
# keyword list dilutes the bias and starts pulling unrelated audio toward these
# terms. Extend per deployment with `openai_transcription_keywords`.
DEFAULT_KEYWORDS: tuple[str, ...] = (
    "BPMN",
    "DeliR",
    "processo",
    "sottoprocesso",
    "gateway",
    "attività",
    "evento",
    "handoff",
    "SLA",
    "KPI",
    "backlog",
    "onboarding",
    "workflow",
)

# The prompt must be written in the language of the audio, so we only have one
# per language we can actually phrase. A language with no entry gets no prompt
# rather than an English one, which would itself pull the transcript off-language.
_PROMPT_BY_LANGUAGE: dict[str, str] = {
    "it": (
        "Intervista di consulenza in italiano su processi aziendali. "
        "Trascrivi solo il parlato effettivo, senza inventare frasi nei silenzi. "
        "Termini ricorrenti: {keywords}."
    ),
    "en": (
        "Business process consulting interview in English. "
        "Transcribe only speech that is actually present; do not invent text over silence. "
        "Recurring terms: {keywords}."
    ),
}


def resolve_keywords(extra: str | None = None) -> list[str]:
    """Domain vocabulary: the built-in list plus deployment-specific terms."""
    keywords = list(DEFAULT_KEYWORDS)

    for term in (extra or "").split(","):
        normalized = term.strip()
        if normalized and normalized not in keywords:
            keywords.append(normalized)

    return keywords


def build_prompt(language: str, keywords: list[str]) -> str | None:
    template = _PROMPT_BY_LANGUAGE.get(language)
    if not template:
        return None

    return template.format(keywords=", ".join(keywords))


def normalize_language(language: str | None, fallback: str) -> str:
    """ISO-639-1 or nothing.

    A malformed code is worse than no code: the API ignores it and we lose the
    lock silently, which is exactly the failure this module exists to stop.
    """
    normalized = (language or "").strip().lower()

    if not normalized:
        return fallback

    if not ISO_639_1.match(normalized):
        raise ValueError(f"Codice lingua non valido: {language!r}. Atteso ISO-639-1, es. 'it'.")

    return normalized


# --- option builders -------------------------------------------------------


def build_transcription_options(
    *,
    model: str,
    language: str,
    keywords: list[str] | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Request options for REST `/v1/audio/transcriptions`, minus `file`."""
    capabilities = capabilities_for(model)
    keywords = keywords or []
    options: dict[str, Any] = {"model": model, "language": language}

    if capabilities.diarized:
        # `diarized_json` is required to get speaker annotations at all, and the
        # diarize model requires a chunking strategy above 30s of audio.
        options["response_format"] = "diarized_json"
        options["chunking_strategy"] = "auto"

    if capabilities.supports_temperature and temperature is not None:
        options["temperature"] = temperature

    if capabilities.supports_keywords and keywords:
        options["keywords"] = keywords

    if capabilities.supports_prompt:
        prompt = build_prompt(language, keywords)
        if prompt:
            options["prompt"] = prompt

    return options


def build_live_transcription_options(
    *,
    model: str,
    language: str,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """The `audio.input.transcription` block of a realtime `session.update`."""
    capabilities = capabilities_for(model)
    keywords = keywords or []
    options: dict[str, Any] = {"model": model, "language": language}

    if capabilities.supports_keywords and keywords:
        options["keywords"] = keywords

    if capabilities.supports_prompt:
        prompt = build_prompt(language, keywords)
        if prompt:
            options["prompt"] = prompt

    return options


def build_live_turn_detection(
    *,
    silence_duration_ms: int,
    prefix_padding_ms: int,
    threshold: float,
) -> dict[str, Any]:
    """Server-side VAD config for the realtime session.

    The alternative --- what this replaced --- was committing the audio buffer
    every 1.5 seconds on a wall clock. That cuts on elapsed time rather than on
    speech, so words get split mid-syllable and each fragment is then language-
    detected on its own, which is one of the ways an Italian interview ends up
    with a Korean line in it. Server VAD cuts on silence instead.

    `silence_duration_ms` defaults higher than the API's own 500ms because a
    consulting interview is full of thinking pauses, and a turn that closes
    inside one splits a single sentence into two independently decoded chunks.
    """
    return {
        "type": "server_vad",
        "silence_duration_ms": silence_duration_ms,
        "prefix_padding_ms": prefix_padding_ms,
        "threshold": threshold,
    }


# --- language guard --------------------------------------------------------

# Expected Unicode script per language we transcribe. A language absent here is
# not guessed at: the guard becomes a passthrough rather than risk deleting a
# correct transcript.
_EXPECTED_SCRIPT_BY_LANGUAGE: dict[str, str] = {
    "it": "LATIN",
    "en": "LATIN",
    "fr": "LATIN",
    "es": "LATIN",
    "de": "LATIN",
    "pt": "LATIN",
    "nl": "LATIN",
}

# Below this many letters a segment carries too little evidence to judge --- an
# interjection like "ok" or a proper noun would trip the ratio on its own.
MIN_LETTERS_FOR_SCRIPT_CHECK = 8

# A correct Italian segment quoting a foreign term still lands far above this;
# a segment the model rendered in another script lands near zero.
MIN_EXPECTED_SCRIPT_RATIO = 0.7


def _script_of(character: str) -> str | None:
    try:
        return unicodedata.name(character).split(" ", 1)[0]
    except ValueError:
        return None


def is_off_script(text: str, expected_script: str) -> bool:
    """True when `text` is written in a script the target language does not use."""
    letters = [character for character in text if character.isalpha()]

    if len(letters) < MIN_LETTERS_FOR_SCRIPT_CHECK:
        return False

    matching = sum(1 for character in letters if _script_of(character) == expected_script)

    return matching / len(letters) < MIN_EXPECTED_SCRIPT_RATIO


@dataclass(frozen=True)
class LanguageGuardResult:
    segments: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    dropped_segments: int = 0


def enforce_language(
    *,
    language: str,
    segments: list[dict[str, Any]] | None,
    text: str,
) -> LanguageGuardResult:
    """Drop the parts of a transcript that came back in the wrong script.

    Applied per segment when the model diarized, per line otherwise, so one bad
    chunk costs that chunk and not the whole interview.
    """
    expected_script = _EXPECTED_SCRIPT_BY_LANGUAGE.get(language)

    if not expected_script:
        return LanguageGuardResult(segments=list(segments or []), text=text)

    kept = [
        segment
        for segment in segments or []
        if not (
            isinstance(segment, dict)
            and is_off_script(str(segment.get("text") or ""), expected_script)
        )
    ]
    kept_lines = [line for line in text.splitlines() if not is_off_script(line, expected_script)]

    # The raw `text` is only read when the model returned no segments, so
    # counting both would double-report the same dropped speech.
    if segments:
        dropped = len(segments) - len(kept)
    else:
        dropped = len(text.splitlines()) - len(kept_lines)

    if dropped:
        logger.warning(
            "transcription language guard dropped %d off-script parts (expected %s for %r)",
            dropped,
            expected_script,
            language,
        )

    return LanguageGuardResult(
        segments=kept,
        text="\n".join(kept_lines).strip(),
        dropped_segments=dropped,
    )


def filter_live_transcript(text: str, language: str) -> str:
    """Same guard for a single realtime item; empty string means it was dropped."""
    expected_script = _EXPECTED_SCRIPT_BY_LANGUAGE.get(language)

    if not expected_script:
        return text

    if is_off_script(text, expected_script):
        logger.warning("live transcription guard dropped an off-script item (expected %s)", expected_script)
        return ""

    return text
