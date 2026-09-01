"""Engine per lo stato operativo (workspace / chat / indice episodico).

Vive su Postgres — database `workspace`, ruolo `delir_workspace` — punto e
basta. Niente fallback SQLite: e' un prodotto, non deve avere il single-writer
e i lock su file di SQLite.

`WORKSPACE_DATABASE_URL` e' obbligatoria; senza, l'app non parte. I tre moduli
(`workspace_storage`, `database`, `episodic_store`) condividono UN engine /
pool: tabelle distinte per nome nello stesso database.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.settings import settings

_MISSING = (
    "WORKSPACE_DATABASE_URL non configurata. Lo stato operativo gira su "
    "Postgres (database `workspace`): avvia lo stack (`cd ops && docker compose "
    "up -d`) e imposta la DSN. Vedi ops/README.md."
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _REPO_ROOT / "alembic_workspace.ini"


@lru_cache(maxsize=1)
def local_engine() -> Engine:
    """Engine condiviso verso il database operativo Postgres.

    Pool contenuto: e' un solo processo app, e i connection budget vanno divisi
    con il canonical, Mem0 e il checkpointer LangGraph."""
    if not settings.workspace_database_url:
        raise RuntimeError(_MISSING)
    return create_engine(
        settings.workspace_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        future=True,
    )


@lru_cache(maxsize=1)
def ensure_schema() -> None:
    """Porta il database operativo a head (Alembic `migrations_workspace`).

    Idempotente e veloce quando gia' aggiornato. Chiamato dal lifespan
    dell'app e dai test; niente DDL all'import dei moduli."""
    if not settings.workspace_database_url:
        raise RuntimeError(_MISSING)
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")
