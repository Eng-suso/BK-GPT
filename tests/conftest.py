# conftest.py — shared pytest fixtures
import pytest

from backend.settings import settings


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
