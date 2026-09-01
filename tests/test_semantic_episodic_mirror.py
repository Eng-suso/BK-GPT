"""semantic_store / episodic_store specchiano sul canonical in modo sincrono
(la add su Mem0 resta unica; il mirror registra solo canonical + audit log).

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

from backend.memory import mem0_client  # noqa: E402
from backend.memory.episodic import episodic_store  # noqa: E402
from backend.memory.models import ConsultantSemanticMemory  # noqa: E402
from backend.memory.semantic import semantic_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _consultant_ctx(conn):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": settings.default_consultant_id},
    )
    conn.execute(text("SELECT set_config('app.current_client_id', '', true)"))


def test_semantic_store_mirrors_synchronously():
    marker = uuid.uuid4().hex[:8]
    statement = f"Il consulente vuole slide brevi [{marker}]."
    memory = ConsultantSemanticMemory(
        category="communication", statement=statement, durability="preference",
    )

    result = semantic_store.save_structured_consultant_memory(memory)
    assert result.startswith("Ho salvato in memoria")

    with MIGRATOR.begin() as conn:
        _consultant_ctx(conn)
        row = conn.execute(
            text("SELECT id, kind, statement FROM semantic_memory WHERE statement = :s"),
            {"s": statement},
        ).one()
        assert row.kind == "preference"

        log_row = conn.execute(
            text(
                "SELECT applied_at, mem0_memory_id, op FROM mem0_projection_log "
                "WHERE memory_kind = 'semantic' AND memory_id = :m"
            ),
            {"m": str(row.id)},
        ).one()
        assert log_row.op == "add"
        # `applied_at` e' gia' valorizzato quando Mem0 ha estratto un fatto sul
        # momento (mem0_memory_id noto); se l'LLM non ha estratto nulla la riga
        # resta pending e la applica il worker.
        if log_row.mem0_memory_id:
            assert log_row.applied_at is not None

        conn.execute(text("DELETE FROM semantic_memory WHERE id = :i"), {"i": row.id})

    if log_row.mem0_memory_id:
        m = mem0_client.get_memory()
        try:
            m.delete(memory_id=log_row.mem0_memory_id)
        except Exception:
            pass


def test_episodic_store_mirrors_synchronously():
    marker = uuid.uuid4().hex[:8]
    title = f"Nota di test {marker}"

    result = episodic_store.save_episode_memory(
        episode_type="note",
        title=title,
        raw_content=f"Contenuto di prova per il mirror episodic [{marker}].",
        summary=f"Sintesi di prova [{marker}]",
    )
    assert "Episodio salvato" in result

    with MIGRATOR.begin() as conn:
        _consultant_ctx(conn)
        row = conn.execute(
            text("SELECT id, episode_type FROM episodic_memory WHERE title = :t"),
            {"t": title},
        ).one()
        assert row.episode_type == "note"

        log_row = conn.execute(
            text(
                "SELECT applied_at, mem0_memory_id FROM mem0_projection_log "
                "WHERE memory_kind = 'episodic' AND memory_id = :m"
            ),
            {"m": str(row.id)},
        ).one()
        if log_row.mem0_memory_id:
            assert log_row.applied_at is not None

        conn.execute(text("DELETE FROM episodic_memory WHERE id = :i"), {"i": row.id})
