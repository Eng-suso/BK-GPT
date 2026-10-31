"""Porta a head entrambi i database, una sola volta anche con piu' container.

    uv run python -m scripts.migrate

E' il primo comando del container di produzione, prima dell'app (che li' gira
con `RUN_MIGRATIONS_ON_STARTUP=false`). Due tracce Alembic: il canonical
(`alembic.ini`, ruolo `delir_migrator`) e il database operativo
(`alembic_workspace.ini`, ruolo `delir_workspace`).

Perche' il lock. In un rilascio senza interruzione il container nuovo parte
mentre il vecchio gira ancora, e dopo un crash due avvii possono sovrapporsi:
due migrazioni parallele sullo stesso schema si pestano. Un advisory lock di
Postgres le mette in fila: il secondo aspetta, poi trova lo schema gia' a head
e non fa niente.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from backend.settings import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Numero fisso del lock: tutti i migratori di DeliR chiedono lo stesso.
MIGRATION_LOCK_KEY = 7_340_211_001


def psycopg_url(url: str) -> str:
    """Il DSN di SQLAlchemy (`postgresql+psycopg://`) nella forma che psycopg accetta."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def migration_lock() -> Iterator[None]:
    """Tiene il lock per tutta la migrazione, su una connessione sua.

    Il lock vive nel database `workspace`, l'unico sempre presente. Se il
    processo muore, Postgres chiude la connessione e libera il lock.
    """
    if not settings.workspace_database_url:
        raise RuntimeError("WORKSPACE_DATABASE_URL non configurata: non c'e' niente da migrare.")
    with psycopg.connect(psycopg_url(settings.workspace_database_url), autocommit=True) as connection:
        logger.info("migrazioni: in attesa del lock")
        connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))


def _upgrade(ini: str) -> None:
    config = Config(str(PROJECT_ROOT / ini))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def run_migrations() -> None:
    """Canonical (se configurato) e workspace a head, sotto lock."""
    with migration_lock():
        if settings.canonical_migrator_url:
            logger.info("migrazioni: canonical")
            _upgrade("alembic.ini")
        else:
            logger.warning("migrazioni: CANONICAL_MIGRATOR_URL assente, canonical saltato")
        logger.info("migrazioni: workspace")
        _upgrade("alembic_workspace.ini")
    logger.info("migrazioni: entrambi i database a head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_migrations()
