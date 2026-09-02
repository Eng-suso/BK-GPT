"""Gateway INV-9: `memory_search` interroga Mem0 con lo scope iniettato.

Skip senza MEM0_DATABASE_URL + OPENAI_API_KEY.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not (settings.mem0_database_url and settings.openai_api_key):
    pytest.skip("servono MEM0_DATABASE_URL + OPENAI_API_KEY", allow_module_level=True)

from backend.memory import gateway, mem0_client  # noqa: E402
from backend.memory.semantic import semantic_store  # noqa: E402


@pytest.fixture()
def seeded_memory(monkeypatch):
    # nome proprio inventato: Mem0 estrae il fatto ma tiene i nomi propri
    monkeypatch.setattr(settings, "mem0_user_id", f"test-{uuid.uuid4()}")
    token = "Zbrunk" + uuid.uuid4().hex[:6]
    statement = (
        f"Il consulente {token} valida gli SLA con una checklist prima di ogni intervista."
    )
    _, mem0_id = semantic_store.add_mem0_memory_with_id(statement)
    if not mem0_id:
        pytest.skip("Mem0 non ha estratto nessuna memoria dal fatto seminato")
    yield token, mem0_id
    try:
        mem0_client.get_memory().delete(memory_id=mem0_id)
    except Exception:
        pass


def test_memory_search_returns_scoped_matches(seeded_memory):
    token, _ = seeded_memory

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        query=f"come valida gli SLA il consulente {token}?",
        limit=5,
    )

    assert result["status"] == "ok"
    assert result["count"] == len(result["matches"])
    blob = " ".join(m["memory"] or "" for m in result["matches"])
    assert token in blob
    # forma stabile del match
    first = result["matches"][0]
    assert set(first) == {"memory_id", "memory", "score", "client_scoped"}


def test_consultant_level_memory_visible_in_a_client_context(seeded_memory):
    token, _ = seeded_memory

    # memoria consultant-level (senza client_id) -> visibile anche passando un client
    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        client_id=str(uuid.uuid4()),
        query=f"come valida gli SLA il consulente {token}?",
        limit=5,
    )

    assert result["status"] == "ok"
    assert all(m["client_scoped"] is False for m in result["matches"])
    blob = " ".join(m["memory"] or "" for m in result["matches"])
    assert token in blob


def test_memory_search_disabled_is_explicit(monkeypatch):
    monkeypatch.setattr(
        mem0_client, "get_memory", lambda: mem0_client.Mem0Disabled("test disabled")
    )
    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id, query="qualsiasi"
    )
    assert result == {
        "status": "not_configured",
        "matches": [],
        "count": 0,
        "reason": "test disabled",
    }
