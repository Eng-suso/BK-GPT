# conftest.py — shared pytest fixtures
import pytest


@pytest.fixture(autouse=False)
def mock_env(monkeypatch):
    """Override environment variables for testing without real API keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-ci")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-fake-key-for-ci")
