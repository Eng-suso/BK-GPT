"""Pattern extraction: da episodi ricorrenti a un playbook candidate (L2 / P7.2).

Prende N `episodic_memory` recenti dello stesso progetto/tema e chiede a un LLM
di estrarre un metodo riutilizzabile — quando si applica, i passi, cosa evitare.
Il risultato e' un `procedural_memory` candidate (scope 'client' di default,
`derived_from` = gli id degli episodi). NON diventa 'active': serve la
promozione col guardrail (P7.1).

L'LLM e' iniettabile cosi' i test restano ermetici. E' un runnable con
`with_structured_output`: `invoke(messages)` ritorna direttamente il modello
Pydantic (`ExtractedPlaybook` / `GeneralizedPlaybook`), stesso pattern di
`backend/process_understanding.py`.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from backend.llm_streaming import stream_to_final
from backend.llm_config import chat_openai_kwargs
from backend.settings import settings

logger = logging.getLogger(__name__)

_MIN_EPISODES = 2
_MAX_EPISODES = 12
_KINDS = {"playbook", "heuristic", "checklist"}


class ExtractedPlaybook(BaseModel):
    kind: str = Field(default="playbook", description="playbook | heuristic | checklist")
    title: str = Field(description="Titolo breve del metodo")
    applies_when: str = Field(default="", description="Quando si applica")
    body: str = Field(description="Il metodo: quando si applica, i passi, cosa evitare")
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)


class GeneralizedPlaybook(BaseModel):
    title: str = Field(description="Titolo generico del metodo")
    applies_when: str = Field(default="", description="Quando si applica, senza riferimenti cliente")
    body: str = Field(description="Il metodo generalizzato, senza nomi cliente ne' dati riservati")


@lru_cache(maxsize=1)
def _extract_llm() -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(**chat_openai_kwargs()).with_structured_output(ExtractedPlaybook)


@lru_cache(maxsize=1)
def _generalize_llm() -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(**chat_openai_kwargs()).with_structured_output(GeneralizedPlaybook)


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
                "degli episodi. Scrivi in italiano. Il campo body deve dire: quando "
                "si applica, i passi in ordine, e cosa evitare. Se gli episodi non "
                "contengono un metodo generalizzabile lascia title e body vuoti. "
                "Restituisci solo lo schema strutturato richiesto."
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

    model = llm if llm is not None else (_extract_llm() if settings.openai_api_key else None)
    if model is None:
        return None

    try:
        result = stream_to_final(model, _build_prompt(episodes))
    except Exception:  # noqa: BLE001 — l'estrazione e' best-effort
        logger.warning("extraction: stream LLM fallito", exc_info=True)
        return None

    if not isinstance(result, ExtractedPlaybook):
        return None

    title = (result.title or "").strip()
    body = (result.body or "").strip()
    if not title or not body:
        return None

    kind = (result.kind or "playbook").strip().lower()
    if kind not in _KINDS:
        kind = "playbook"

    # `confidence` e' gia' in [0, 1]: lo garantisce lo schema Pydantic validato
    # da `with_structured_output`.
    return ExtractedPlaybook(
        kind=kind,
        title=title,
        applies_when=(result.applies_when or "").strip(),
        body=body,
        confidence=result.confidence,
    )


def _build_generalize_prompt(playbook: dict[str, Any], client_names: list[str]) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    names = ", ".join(n for n in client_names if n) or "(nessuno noto)"
    source = "\n".join(
        part
        for part in (
            f"Titolo: {playbook.get('title') or ''}",
            f"Si applica quando: {playbook.get('applies_when') or ''}",
            f"Corpo:\n{playbook.get('body') or ''}",
        )
        if part
    )
    return [
        SystemMessage(
            content=(
                "Sei l'analista di metodo di un consulente. Ti do un playbook nato "
                "per un singolo cliente. Riscrivilo come metodo GENERICO, riutilizzabile "
                "con qualsiasi cliente: togli i nomi dei clienti, i nomi di persona, i "
                "numeri riservati (importi, percentuali contrattuali, tempi specifici), "
                "i dettagli non trasferibili. Mantieni i passi e la logica. Non "
                f"reintrodurre questi nomi cliente: {names}. Se non resta un metodo "
                "generalizzabile lascia title e body vuoti. Restituisci solo lo schema "
                "strutturato richiesto."
            )
        ),
        HumanMessage(content=source[:6000]),
    ]


def generalize_playbook_body(
    playbook: dict[str, Any],
    client_names: list[str],
    *,
    llm: Any | None = None,
) -> GeneralizedPlaybook | None:
    """Riscrive un playbook client-scoped come metodo generico (P7.3).

    `None` se l'LLM non e' disponibile o non resta un metodo. Il verdetto finale
    su "abbastanza generico" resta al guardrail in fase di promote.
    """
    model = llm if llm is not None else (_generalize_llm() if settings.openai_api_key else None)
    if model is None:
        return None

    try:
        result = stream_to_final(model, _build_generalize_prompt(playbook, client_names))
    except Exception:  # noqa: BLE001
        logger.warning("generalize: stream LLM fallito", exc_info=True)
        return None

    if not isinstance(result, GeneralizedPlaybook):
        return None

    title = (result.title or "").strip()
    body = (result.body or "").strip()
    if not title or not body:
        return None
    return GeneralizedPlaybook(
        title=title,
        applies_when=(result.applies_when or "").strip(),
        body=body,
    )
