"""Embedding contract v1 del knowledge graph (INV-4).

Un solo modello, una sola dimensione, nessun fallback muto: `text-embedding-
3-small` / 1536. Usato per `kg_chunk` (indice vettoriale KG, P3) e, in
prospettiva, per `kg_entity.embedding` (entity resolution, P2).

Senza `OPENAI_API_KEY` l'embedding e' disattivato: `embed_texts` ritorna
`None` e i chiamanti degradano (il retrieval ricade sul match per nome).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from backend.settings import settings

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
EMBED_VERSION = 1


def available() -> bool:
    return bool(settings.openai_api_key)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Un embedding per testo, stesso ordine. `None` se l'embedding non e'
    disponibile o la chiamata fallisce — mai solleva."""
    if not texts or not available():
        return None
    clean = [t if isinstance(t, str) and t.strip() else " " for t in texts]
    try:
        resp = _client().embeddings.create(
            model=EMBED_MODEL, input=clean, dimensions=EMBED_DIM
        )
        return [item.embedding for item in resp.data]
    except Exception as exc:  # noqa: BLE001 — l'embedding non deve far fallire il chiamante
        logger.warning("embed_texts fallito: %s", exc)
        return None


def embed_query(text_value: str) -> list[float] | None:
    out = embed_texts([text_value or " "])
    return out[0] if out else None


def to_pgvector(vector: list[float] | None) -> str | None:
    """Serializza un embedding nel literal testuale accettato da `CAST(:x AS vector)`."""
    if not vector:
        return None
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
