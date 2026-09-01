"""Engine per lo stato operativo locale (workspace / chat / indice episodico).

Un solo posto decide dove vive: Postgres (`settings.workspace_database_url`,
database `workspace` di proprieta' del ruolo `delir_workspace`) oppure il
fallback SQLite per dev/CI.

SQLite qui e' fragile — single-writer, lock su tutto il file, backup a rischio —
quindi in prod la DSN Postgres va sempre configurata. Il fallback resta solo
per non imporre un Postgres a chi lancia i test o gira in locale veloce.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from backend.settings import settings

DATA_DIR = Path("data")


def using_postgres() -> bool:
    return bool(settings.workspace_database_url)


def local_engine(sqlite_filename: str) -> Engine:
    """Engine per un modulo di stato operativo.

    Con `workspace_database_url` -> Postgres condiviso (pool reale). Senza ->
    SQLite in `data/<sqlite_filename>` con WAL + busy_timeout per limitare i
    "database is locked".
    """
    if using_postgres():
        return create_engine(
            settings.workspace_database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            future=True,
        )

    sqlite_path = DATA_DIR / sqlite_filename
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{sqlite_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
