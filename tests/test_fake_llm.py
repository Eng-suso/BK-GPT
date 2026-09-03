"""`DELIR_FAKE_LLM=1` swaps the agent runtime for a deterministic stub.

Guards the seam used by e2e / contract runs: the chat path must answer without
any OpenAI call, without compiling the LangGraph agent, and without touching
the checkpoint database — while keeping the normal event shape.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    """Enable deterministic fake-LLM mode and clear the OpenAI API key for a test."""
    monkeypatch.setattr(settings, "delir_fake_llm", True)
    monkeypatch.setattr(settings, "openai_api_key", None)


# --- transport-free: the runtime seam itself -------------------------------

def test_stream_agent_text_is_deterministic_without_model_or_db():
    from backend.services.agent_runtime import stream_agent_text

    text = stream_agent_text(
        thread_id="t-fake-1",
        model_name="gpt-5.6-luna",
        messages=[{"role": "user", "content": "ciao"}],
        scope=None,
    )

    assert text.startswith("[fake-llm]")
    assert "ciao" in text
    assert "consultant" in text


def test_stream_agent_events_emits_start_delta_and_no_error():
    from backend.services.agent_runtime import stream_agent_events

    events = list(
        stream_agent_events(
            thread_id="t-fake-2",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "analizza"}],
            scope=None,
        )
    )

    types = [event.type for event in events]
    assert types[0] == "start"
    assert "delta" in types
    assert "error" not in types

    streamed = "".join(e.content or "" for e in events if e.type == "delta")
    assert streamed.startswith("[fake-llm]")


def test_fake_agent_never_builds_the_real_agent(monkeypatch):
    import backend.services.agent_runtime as runtime

    def _boom(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("get_agent must not be called in fake-llm mode")

    monkeypatch.setattr(runtime, "get_agent", _boom)

    text = runtime.stream_agent_text(
        thread_id="t-fake-3",
        model_name="gpt-5.6-luna",
        messages=[{"role": "user", "content": "x"}],
        scope=None,
    )
    assert text.startswith("[fake-llm]")


# --- full HTTP path (needs the workspace DB for session persistence) -------

_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as c:
        yield c


@_needs_db
def test_streaming_endpoint_emits_delta_and_done(client: TestClient):
    created = client.post(
        "/v1/consultant-chat/sessions",
        json={"model_name": "gpt-5.6-luna", "scope": {"type": "consultant"}},
    )
    assert created.status_code == 200, created.text
    thread_id = created.json()["thread_id"]

    with client.stream(
        "POST",
        f"/v1/consultant-chat/sessions/{thread_id}/messages/stream",
        json={
            "message": "analizza il processo",
            "model_name": "gpt-5.6-luna",
            "scope": {"type": "consultant"},
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    types = [event["type"] for event in events]
    assert "delta" in types
    assert types[-1] == "done"
    assert "error" not in types
    assert events[-1]["message"].startswith("[fake-llm]")
