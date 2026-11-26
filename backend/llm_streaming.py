from __future__ import annotations

from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig

INTERNAL_STREAM_METADATA_KEY = "delir_stream_visibility"
INTERNAL_STREAM_METADATA_VALUE = "internal"

#: Il tag dei client della chat (`llm.chat_client`): gli unici la cui spesa la
#: scrive il runtime del turno, sommando lo stream. Tutto il resto che passa
#: nello stream di un turno - le chiamate del gateway fatte dai tool, che
#: LangGraph inoltra come le altre - scrive gia' la sua riga da se'. Contare
#: solo cio' che porta questo tag, invece di escludere cio' che non va contato,
#: e' cio' che impedisce a un client nuovo di finire contato due volte.
TURN_METERED_TAG = "delir:turn-metered"


class StreamableRunnable(Protocol):
    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        ...


def _merge_stream_chunk(current: Any, chunk: Any) -> Any:
    if current is None:
        return chunk

    try:
        return current + chunk
    except TypeError:
        if isinstance(current, dict) and isinstance(chunk, dict):
            return {**current, **chunk}
        return chunk


def _internal_stream_config(config: RunnableConfig | None) -> RunnableConfig:
    base: dict[str, Any] = dict(config or {})
    metadata = dict(base.get("metadata") or {})
    tags = list(base.get("tags") or [])
    metadata[INTERNAL_STREAM_METADATA_KEY] = INTERNAL_STREAM_METADATA_VALUE
    if INTERNAL_STREAM_METADATA_VALUE not in tags:
        tags.append(INTERNAL_STREAM_METADATA_VALUE)
    base["metadata"] = metadata
    base["tags"] = tags
    return base


def stream_to_final(
    runnable: StreamableRunnable,
    input: Any,
    config: RunnableConfig | None = None,
    **kwargs: Any,
) -> Any:
    result = None
    for chunk in runnable.stream(input, config=_internal_stream_config(config), **kwargs):
        result = _merge_stream_chunk(result, chunk)
    return result


def stream_to_text(
    runnable: StreamableRunnable,
    input: Any,
    config: RunnableConfig | None = None,
    **kwargs: Any,
) -> str:
    result = stream_to_final(runnable, input, config=config, **kwargs)
    return str(getattr(result, "content", result) or "")
