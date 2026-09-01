"""Checkpointer LangGraph su Postgres — stato delle conversazioni.

Vive nel database operativo `workspace` (stessa DSN di `local_store`). Niente
SQLite: lo stato di una conversazione non puo' stare su un file single-writer.
"""

from __future__ import annotations

import atexit
import logging
from functools import lru_cache

from backend.settings import settings

logger = logging.getLogger(__name__)


def _conninfo() -> str:
    url = settings.workspace_database_url
    if not url:
        raise RuntimeError(
            "WORKSPACE_DATABASE_URL non configurata: serve per il checkpointer "
            "LangGraph (stato conversazioni). Vedi ops/README.md."
        )
    # psycopg vuole lo scheme puro, senza il dialetto SQLAlchemy
    return url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache(maxsize=1)
def get_checkpointer():
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=_conninfo(),
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    saver = PostgresSaver(pool)
    saver.setup()  # idempotente: crea le tabelle di checkpoint se mancano
    return saver


@atexit.register
def _close() -> None:
    if get_checkpointer.cache_info().currsize == 0:
        return
    try:
        get_checkpointer().conn.close()
    except Exception:  # noqa: BLE001
        pass
