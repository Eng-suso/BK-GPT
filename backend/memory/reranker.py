"""Reranker dei passaggi di contesto del retrieval (P3.2).

Dopo la fusione RRF (`gateway._text_search`) i chunk sono ordinati da due
segnali lessicali/vettoriali che stimano la *somiglianza*, non la *risposta
alla domanda*. Un giudice LLM (temperature 0, output strutturato) riordina i
primi N per rilevanza effettiva alla query — stessa filosofia del resolver di
P2: segnali economici per il recall, LLM per il giudizio.

Confine esplicito:
  - `Reranker` e' un `Protocol`: `LLMReranker` e' l'implementazione MVP, ma un
    cross-encoder (sentence-transformers, Cohere, ...) puo' subentrare dietro
    la stessa interfaccia senza toccare il gateway.
  - l'ordine restituito dall'LLM e' input non fidato: validato (indici in
    range, deduplicati) prima dell'uso; su qualsiasi errore -> identita'
    (nessun riordino), loggato.

Off di default (`settings.retrieval_rerank_enabled`): aggiunge una chiamata di
rete sul path di grounding dell'agente.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Protocol

from pydantic import BaseModel, Field

from backend.llm_streaming import stream_to_final
from backend.settings import settings

logger = logging.getLogger(__name__)

# Quanti passaggi passare al giudice: oltre, il costo/latenza non vale il
# guadagno e il prompt si sporca.
MAX_PASSAGES = 12
_SNIPPET_CHARS = 600


class Reranker(Protocol):
    def order(self, query: str, passages: Sequence[str]) -> list[int]:
        """Indici dei `passages` dal piu' al meno rilevante per `query`.

        Puo' ometterne (lunghezza <= input). Gli indici sono 0-based, unici,
        in `range(len(passages))`.
        """
        ...


class _RerankVerdict(BaseModel):
    """Schema del giudizio LLM (trust boundary -> Pydantic)."""

    order: list[int] = Field(
        default_factory=list,
        description="Indici 0-based dei passaggi, dal piu' al meno rilevante alla domanda.",
    )


def _sanitize(order: Sequence[Any], n: int) -> list[int]:
    """Ordine LLM (non fidato) -> lista di indici validi, deduplicati, in range.

    I passaggi non citati dall'LLM restano in coda nel loro ordine originale:
    non si perde mai un candidato.
    """
    seen: set[int] = set()
    clean: list[int] = []
    for raw in order or []:
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n and idx not in seen:
            seen.add(idx)
            clean.append(idx)
    clean.extend(i for i in range(n) if i not in seen)
    return clean


class LLMReranker:
    """Giudice LLM: una chiamata strutturata, ordine sanificato, fallback identita'."""

    def __init__(self, llm: Any):
        self._llm = llm

    def order(self, query: str, passages: Sequence[str]) -> list[int]:
        n = len(passages)
        if n <= 1:
            return list(range(n))
        try:
            verdict = stream_to_final(self._llm, _build_prompt(query, passages))
        except Exception:  # noqa: BLE001 — il rerank e' best-effort, mai fatale
            logger.warning("reranker: stream LLM fallito", exc_info=True)
            return list(range(n))
        raw_order = getattr(verdict, "order", None)
        if raw_order is None and isinstance(verdict, dict):
            raw_order = verdict.get("order")
        return _sanitize(raw_order or [], n)


def _build_prompt(query: str, passages: Sequence[str]) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    lines = [f"DOMANDA: {query.strip()}", "", "PASSAGGI:"]
    for i, passage in enumerate(passages):
        lines.append(f"[{i}] {passage.strip()[:_SNIPPET_CHARS]}")
    lines.append(
        "\nOrdina gli indici dei passaggi dal piu' utile a rispondere alla "
        "domanda al meno utile. Includi solo quelli almeno in parte pertinenti."
    )
    return [
        SystemMessage(
            content=(
                "Sei l'analista di un consulente di processo. Ricevi una domanda "
                "e una lista di passaggi estratti da documenti/interviste. "
                "Riordina i passaggi per quanto ciascuno aiuta a rispondere alla "
                "domanda: chi risponde direttamente prima, chi da' solo contesto "
                "dopo, chi e' fuori tema per ultimo o omesso. Restituisci solo lo "
                "schema richiesto."
            )
        ),
        HumanMessage(content="\n".join(lines)),
    ]


@lru_cache(maxsize=1)
def build_reranker() -> Reranker | None:
    """`LLMReranker` dai settings, o `None` se non c'e' un LLM."""
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from backend.llm_config import chat_openai_kwargs

        llm = ChatOpenAI(**chat_openai_kwargs()).with_structured_output(_RerankVerdict)
    except Exception:  # noqa: BLE001
        logger.warning("reranker: LLM non inizializzabile", exc_info=True)
        return None
    return LLMReranker(llm)


def _truncate(items: list[dict[str, Any]], top_n: int | None) -> list[dict[str, Any]]:
    # top_n=None -> tutti; top_n=0 -> lista vuota (limite esplicito, non falsy)
    return items if top_n is None else items[: max(top_n, 0)]


def rerank_passages(
    query: str,
    items: list[dict[str, Any]],
    *,
    key: str = "content",
    reranker: Reranker | None = None,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Riordina `items` (dict con testo in `item[key]`) per rilevanza a `query`.

    `reranker` iniettabile per i test; se `None` se ne costruisce uno dai
    settings. Senza reranker e senza query -> `items` invariati (troncati a
    `top_n` se dato). Ogni item riordinato prende `rerank_position` (0-based).
    """
    if not items or not (query or "").strip():
        return _truncate(items, top_n)

    model = reranker if reranker is not None else build_reranker()
    if model is None:
        return _truncate(items, top_n)

    head = items[:MAX_PASSAGES]
    tail = items[MAX_PASSAGES:]
    order = model.order(query, [str(it.get(key, "")) for it in head])

    ranked = [{**head[i], "rerank_position": pos} for pos, i in enumerate(order)]
    return _truncate(ranked + tail, top_n)
