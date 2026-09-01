"""Pipeline canonical_memory -> mem0_projection_log -> worker -> Mem0 OSS (P1).

Skip senza le DSN Postgres + MEM0_DATABASE_URL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.mem0_database_url,
)
if not all(_NEEDED):
    pytest.skip(
        "servono CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL / "
        "CANONICAL_WORKER_URL / MEM0_DATABASE_URL",
        allow_module_level=True,
    )

from backend.memory import canonical_memory, mem0_client  # noqa: E402
from backend.workers.mem0_worker import drain_once  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


@pytest.fixture()
def consultant_id():
    cid = uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'m0')"),
            {"i": cid, "e": f"{cid}@t.local"},
        )
    yield str(cid)
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": cid})
    memory = mem0_client.get_memory()
    if not hasattr(memory, "reason"):
        try:
            memory.delete_all(user_id=str(cid))
        except Exception:
            pass


def test_semantic_memory_reaches_mem0(consultant_id):
    memory_id = canonical_memory.write_semantic_memory(
        consultant_id,
        kind="preference",
        statement="Il consulente vuole i deliverable in italiano, mai tradotti.",
        category="delivery",
    )

    assert drain_once() >= 1

    with MIGRATOR.begin() as conn:
        row = conn.execute(
            text(
                "SELECT applied_at, mem0_memory_id FROM mem0_projection_log "
                "WHERE memory_id = :m"
            ),
            {"m": memory_id},
        ).one()
    assert row.applied_at is not None
    assert row.mem0_memory_id

    memory = mem0_client.get_memory()
    hits = memory.search(
        query="in che lingua vuole i deliverable?",
        filters={"user_id": consultant_id},
        limit=3,
    )
    texts = " ".join(h.get("memory", "") for h in hits.get("results", []))
    assert "italian" in texts.lower() or "italiano" in texts.lower()


def test_worker_idempotent(consultant_id):
    canonical_memory.write_semantic_memory(
        consultant_id, kind="fact", statement="DeliR usa Prosimos per la simulazione."
    )
    assert drain_once() >= 1
    assert drain_once() == 0
