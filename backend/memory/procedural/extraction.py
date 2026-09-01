"""Pattern extraction: da episodi ricorrenti a un playbook candidate (L2 / P7.2).

Prende N `episodic_memory` recenti dello stesso progetto/tema e chiede a un LLM
di estrarre un metodo riutilizzabile — quando si applica, i passi, cosa evitare.
Il risultato e' un `procedural_memory` candidate (scope 'client' di default,
`derived_from` = gli id degli episodi). NON diventa 'active': serve la
promozione col guardrail (P7.1).

L'LLM e' iniettabile (come nel guardrail) cosi' i test restano ermetici.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from backend.settings import settings

logger = logging.getLogger(__name__)

_MIN_EPISODES = 2
_MAX_EPISODES = 12


class ExtractedPlaybook(BaseModel):
    kind: str = Field(default="playbook", description="playbook | heuristic | checklist")
    title: str = Field(description="Titolo breve del metodo")
    applies_when: str = Field(default="", description="Quando si applica")
    body: str = Field(description="Il metodo: quando si applica, i passi, cosa evitare")
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)


def _supports_reasoning_controls(model: str) -> bool:
    return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))


@lru_cache(maxsize=1)
def _extraction_llm() -> Any:
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "model": settings.openai_model,
        "temperature": 0,
        "timeout": settings.model_timeout_seconds,
        "max_retries": settings.model_max_retries,
        "streaming": False,
        "disable_streaming": True,
    }
    if _supports_reasoning_controls(settings.openai_model):
        kwargs["reasoning_effort"] = "medium"
        kwargs["verbosity"] = "low"
    return ChatOpenAI(**kwargs)


def _format_episodes(episodes: list[dict[str, Any]]) -> str:
    lines = []
    for ep in episodes[:_MAX_EPISODES]:
        lines.append(
            f"- [{ep.get('episode_type') or 'episode'}] "
            f"{ep.get('title') or '(senza titolo)'}"
            + (f" ({ep['occurred_at']})" if ep.get("occurred_at") else "")
            + (f"\n  {ep['summary']}" if ep.get("summary") else "")
        )
    return "\n".join(lines)


def _build_prompt(episodes: list[dict[str, Any]]) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(
            content=(
                "Sei l'analista di metodo di un consulente di processo. Ti do una "
                "serie di episodi (interviste, decisioni, note, feedback) di uno "
                "stesso progetto. Estrai UN metodo riutilizzabile, non un riassunto "
                "degli episodi. Scrivi in italiano. Rispondi SOLO JSON con questa "
                'forma: {"kind":"playbook|heuristic|checklist","title":"...",'
                '"applies_when":"...","body":"...","confidence":0.0}. '
                "Il body deve dire: quando si applica, i passi in ordine, e cosa "
                "evitare. Se gli episodi non contengono un metodo generalizzabile "
                'rispondi {"title":"","body":""}.'
            )
        ),
        HumanMessage(content=_format_episodes(episodes)[:6000]),
    ]


def extract_playbook_from_episodes(
    episodes: list[dict[str, Any]],
    *,
    llm: Any | None = None,
) -> ExtractedPlaybook | None:
    """`ExtractedPlaybook` se gli episodi contengono un metodo, altrimenti None.

    `None` anche se gli episodi sono meno di `_MIN_EPISODES` o se l'LLM non e'
    disponibile / risponde male.
    """
    episodes = [e for e in (episodes or []) if e]
    if len(episodes) < _MIN_EPISODES:
        return None

    model = llm if llm is not None else (_extraction_llm() if settings.openai_api_key else None)
    if model is None:
        return None

    try:
        response = model.invoke(_build_prompt(episodes))
    except Exception:  # noqa: BLE001 — l'estrazione e' best-effort
        logger.warning("extraction: invoke LLM fallito", exc_info=True)
        return None

    content = str(getattr(response, "content", response) or "")
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None

    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title or not body:
        return None

    kind = str(data.get("kind") or "playbook").strip().lower()
    if kind not in {"playbook", "heuristic", "checklist"}:
        kind = "playbook"
    try:
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.4))))
    except (TypeError, ValueError):
        confidence = 0.4

    return ExtractedPlaybook(
        kind=kind,
        title=title,
        applies_when=str(data.get("applies_when") or "").strip(),
        body=body,
        confidence=confidence,
    )
