"""Chi aggiorna lo schema dei database, e quando.

In sviluppo l'app porta il database operativo a head da sola, a ogni avvio:
comodo. In un deploy due container possono partire insieme (rilascio senza
interruzione, riavvio dopo un crash): due migrazioni parallele sullo stesso
schema. In prod lo schema lo aggiorna un solo comando, `scripts.migrate`,
prima dell'app e sotto un lock di Postgres; l'app non lo tocca.
"""
import threading
import time

import psycopg
import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.settings import settings
from scripts import migrate

pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve lo stack di test (WORKSPACE_DATABASE_URL)"
)


def test_with_startup_migrations_off_the_app_leaves_the_schema_alone(monkeypatch):
    import backend.local_store as local_store
    from backend.app import app

    calls: list[str] = []
    monkeypatch.setattr(settings, "run_migrations_on_startup", False)
    monkeypatch.setattr(local_store, "ensure_schema", lambda: calls.append("ensure_schema"))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert calls == []


def test_a_second_migrator_waits_for_the_first(monkeypatch):
    """Due container che partono insieme non migrano in parallelo."""
    holder = psycopg.connect(migrate.psycopg_url(settings.workspace_database_url), autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (migrate.MIGRATION_LOCK_KEY,))
    finished = threading.Event()

    def second_migrator() -> None:
        migrate.run_migrations()
        finished.set()

    thread = threading.Thread(target=second_migrator, daemon=True)
    try:
        thread.start()
        time.sleep(2)
        assert not finished.is_set(), "ha migrato mentre un altro teneva il lock"
    finally:
        holder.execute("SELECT pg_advisory_unlock(%s)", (migrate.MIGRATION_LOCK_KEY,))
        holder.close()

    thread.join(timeout=120)
    assert finished.is_set(), "liberato il lock, la migrazione non e' finita"


def _revision(ini: str, url: str) -> tuple[str | None, str]:
    head = ScriptDirectory.from_config(Config(ini)).get_current_head()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    return current, head


def test_after_the_command_both_databases_are_at_head():
    migrate.run_migrations()

    current, head = _revision("alembic_workspace.ini", settings.workspace_database_url)
    assert current == head
    if settings.canonical_migrator_url:
        current, head = _revision("alembic.ini", settings.canonical_migrator_url)
        assert current == head
