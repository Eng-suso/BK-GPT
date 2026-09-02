# conftest.py — shared pytest fixtures
import time
from collections.abc import Callable

import pytest

from backend.settings import settings


@pytest.fixture()
def wait_projected():
    """drain di `graph_outbox` best-effort + retry finche' `check()` e' vero.

    Robusto a un worker in-process dell'app (uvicorn locale) che drena la stessa
    coda: in quel caso il `drain_once()` esplicito del test vede 0 righe ma la
    proiezione e' comunque avvenuta. Non asserire mai sul valore di ritorno di
    `drain_once()` in un test di integrazione — usare questo.
    """

    def _wait(check: Callable[[], bool], *, tries: int = 15, delay: float = 0.4) -> bool:
        from backend.workers.graph_worker import drain_once

        for _ in range(tries):
            drain_once()
            if check():
                return True
            time.sleep(delay)
        return False

    return _wait


@pytest.fixture(scope="session", autouse=True)
def _operational_schema():
    """Porta il database operativo `workspace` a head una volta per sessione.

    Niente DDL all'import dei moduli: lo schema si crea qui (o dal lifespan
    dell'app in prod). Skip se `WORKSPACE_DATABASE_URL` non e' configurata —
    i test che toccano workspace/chat/episodic si skippano da soli.
    """
    if not settings.workspace_database_url:
        return
    from backend.local_store import ensure_schema

    ensure_schema()


@pytest.fixture(autouse=False)
def mock_env(monkeypatch):
    """Override environment variables for testing without real API keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-ci")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-fake-key-for-ci")
