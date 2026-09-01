"""Mem0 OSS self-hosted — Memory OS degli agenti (D1 / INV-8).

NON il Platform SDK hosted e NON il client MCP: `mem0.Memory` in-process.
- vector store: database `mem0` isolato nello stesso cluster Postgres
  (ruolo delir_mem0), cosi' un bug di Mem0 non tocca lo schema canonical
- LLM + embedder: OpenAI (la key gia' in .env)
- niente graph store: il grafo tipizzato di dominio e' Neo4j, non la
  Graph Memory schema-free di Mem0

Projection ricostruibile (INV-2): la verita' e' in Postgres canonical, qui
c'e' solo il recall. Rebuild = reset dello scope + replay di
mem0_projection_log.

Se `mem0_database_url` non e' configurata, Mem0 e' disattivato e i chiamanti
degradano con un messaggio, senza rompere nulla.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from backend.settings import settings

# Self-hosted: niente telemetria verso l'esterno (coerente con la logica B+).
os.environ.setdefault("MEM0_TELEMETRY", "False")

# Mem0 di default fa estrarre i fatti all'LLM e tende a tradurli in inglese.
# DeliR lavora in italiano: la lingua della fonte va preservata.
_CUSTOM_INSTRUCTIONS = (
    "Preserve the original language of the input verbatim. Never translate. "
    "Extract durable facts, preferences and rules about the consultant and the "
    "engagement; ignore small talk and transient details."
)


@dataclass(frozen=True)
class Mem0Disabled:
    reason: str


def _pg_config() -> dict:
    parsed = urlparse(settings.mem0_database_url or "")
    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/mem0").lstrip("/") or "mem0",
        "collection_name": settings.mem0_collection,
        "embedding_model_dims": 1536,
        "hnsw": True,
    }


def _config() -> dict:
    return {
        "version": "v1.1",
        "custom_instructions": _CUSTOM_INSTRUCTIONS,
        "vector_store": {"provider": "pgvector", "config": _pg_config()},
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.mem0_llm_model,
                "api_key": settings.openai_api_key,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": settings.mem0_embedder_model,
                "api_key": settings.openai_api_key,
                "embedding_dims": 1536,
            },
        },
        "history_db_path": settings.mem0_history_db_path,
    }


@lru_cache(maxsize=1)
def get_memory():
    """Ritorna un'istanza `mem0.Memory` oppure `Mem0Disabled(reason)`."""
    if not settings.openai_api_key:
        return Mem0Disabled("manca OPENAI_API_KEY")
    if not settings.mem0_database_url:
        return Mem0Disabled("manca MEM0_DATABASE_URL (database mem0 non configurato)")
    try:
        from mem0 import Memory

        return Memory.from_config(_config())
    except Exception as exc:  # config errata, DB irraggiungibile, dip mancante
        return Mem0Disabled(f"init fallita: {exc}")


def is_enabled() -> bool:
    return not isinstance(get_memory(), Mem0Disabled)
