"""Il processo puo' servire richieste: database raggiungibili e a head.

Usato da `GET /health/ready`. Ogni controllo dice solo `ok`, `down` o
`behind`: la rotta e' pubblica, e un DSN o un messaggio del driver in una
risposta pubblica e' un'informazione regalata.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.settings import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONNECT_TIMEOUT_SECONDS = 3

Check = Literal["ok", "down", "behind"]


@lru_cache(maxsize=None)
def expected_head(ini: str) -> str | None:
    """La revisione che il codice si aspetta: non cambia finche' il processo vive."""
    return ScriptDirectory.from_config(Config(str(PROJECT_ROOT / ini))).get_current_head()


def _database_check(url: str, ini: str) -> Check:
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(dsn, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except psycopg.Error as exc:
        # Nel log si', nella risposta no.
        logger.warning("readiness: database %s non raggiungibile: %s", ini, exc.__class__.__name__)
        return "down"
    current = row[0] if row else None
    return "ok" if current == expected_head(ini) else "behind"


def readiness_checks() -> dict[str, Check]:
    """Un controllo per database configurato. Il workspace c'e' sempre."""
    checks: dict[str, Check] = {}
    if settings.workspace_database_url:
        checks["workspace"] = _database_check(settings.workspace_database_url, "alembic_workspace.ini")
    else:
        checks["workspace"] = "down"
    if settings.canonical_database_url:
        checks["canonical"] = _database_check(settings.canonical_database_url, "alembic.ini")
    return checks
