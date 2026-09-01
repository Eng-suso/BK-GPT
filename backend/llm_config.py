"""kwargs condivisi per costruire `ChatOpenAI` dai settings.

Un solo posto per la policy sui parametri modello (reasoning controls, timeout,
streaming). Usato dai builder task-scoped (`process_understanding`,
`memory/procedural/extraction`). L'agente runtime (`backend/agent.py`) usa la
sottoclasse `DeliRChatOpenAI` con la sua config di streaming/langsmith e resta
separato di proposito.
"""

from __future__ import annotations

from typing import Any

from backend.settings import settings


def supports_reasoning_controls(model: str) -> bool:
    return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))


def chat_openai_kwargs(
    *,
    max_tokens: int | None = None,
    temperature: float = 0,
    reasoning_effort: str = "medium",
    verbosity: str = "low",
) -> dict[str, Any]:
    """kwargs per `ChatOpenAI(**chat_openai_kwargs())` — non-streaming, task-scoped.

    `reasoning_effort` / `verbosity` sono applicati solo se il modello li
    supporta (`gpt-5*`, `o1/o3/o4*`).
    """
    kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "model": settings.openai_model,
        "temperature": temperature,
        "timeout": settings.model_timeout_seconds,
        "max_retries": settings.model_max_retries,
        "streaming": False,
        "disable_streaming": True,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if supports_reasoning_controls(settings.openai_model):
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["verbosity"] = verbosity
    return kwargs
