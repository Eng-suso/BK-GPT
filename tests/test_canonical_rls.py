"""Isolamento tenant sul Postgres canonical (INV-6 / INV-9).

Richiede un Postgres canonical migrato (docker compose in ops/postgres +
`alembic upgrade head`) e le due DSN in ambiente o in .env:

    CANONICAL_MIGRATOR_URL=postgresql+psycopg://delir_migrator:...@127.0.0.1:55432/delir
    CANONICAL_DATABASE_URL=postgresql+psycopg://delir_app:...@127.0.0.1:55432/delir

Senza, il modulo viene skippato.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from backend.settings import settings

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)
APP = create_engine(settings.canonical_database_url, future=True, poolclass=None)


def _set_ctx(conn, consultant_id, client_id=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant_id)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


@pytest.fixture()
def tenants():
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    a_client, b_client = uuid.uuid4(), uuid.uuid4()

    with MIGRATOR.begin() as conn:
        for cid, name in ((a_id, "cons-a"), (b_id, "cons-b")):
            conn.execute(
                text(
                    "INSERT INTO consultant (id, email, display_name) "
                    "VALUES (:id, :email, :name)"
                ),
                {"id": cid, "email": f"{name}@t.local", "name": name},
            )
        # client + semantic rows di A
        _set_ctx(conn, a_id)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:id, :c, 'A1')"),
            {"id": a_client, "c": a_id},
        )
        _set_ctx(conn, a_id)
        conn.execute(
            text(
                "INSERT INTO semantic_memory (consultant_id, scope, kind, statement) "
                "VALUES (:c, 'consultant', 'concept', 'metodo generale di A')"
            ),
            {"c": a_id},
        )
        _set_ctx(conn, a_id, a_client)
        conn.execute(
            text(
                "INSERT INTO semantic_memory (consultant_id, client_id, scope, kind, statement) "
                "VALUES (:c, :cl, 'client', 'fact', 'A1 usa SAP')"
            ),
            {"c": a_id, "cl": a_client},
        )
        # client + semantic row di B
        _set_ctx(conn, b_id)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:id, :c, 'B1')"),
            {"id": b_client, "c": b_id},
        )
        _set_ctx(conn, b_id, b_client)
        conn.execute(
            text(
                "INSERT INTO semantic_memory (consultant_id, client_id, scope, kind, statement) "
                "VALUES (:c, :cl, 'client', 'fact', 'B1 usa Oracle')"
            ),
            {"c": b_id, "cl": b_client},
        )

    yield {"a": a_id, "b": b_id, "a_client": a_client, "b_client": b_client}

    with MIGRATOR.begin() as conn:
        conn.execute(
            text("DELETE FROM consultant WHERE id = ANY(:ids)"),
            {"ids": [a_id, b_id]},
        )


def test_client_context_sees_only_own_client_and_consultant_rows(tenants):
    with APP.begin() as conn:
        _set_ctx(conn, tenants["a"], tenants["a_client"])
        rows = conn.execute(
            text("SELECT statement FROM semantic_memory ORDER BY statement")
        ).scalars().all()
    assert rows == ["A1 usa SAP", "metodo generale di A"]


def test_consultant_context_sees_only_consultant_scoped_rows(tenants):
    with APP.begin() as conn:
        _set_ctx(conn, tenants["a"])  # nessun client
        rows = conn.execute(text("SELECT statement FROM semantic_memory")).scalars().all()
    assert rows == ["metodo generale di A"]


def test_cross_tenant_rows_are_invisible(tenants):
    with APP.begin() as conn:
        _set_ctx(conn, tenants["a"], tenants["a_client"])
        count = conn.execute(
            text("SELECT count(*) FROM semantic_memory WHERE statement LIKE 'B1%'")
        ).scalar_one()
        clients = conn.execute(text("SELECT name FROM client")).scalars().all()
    assert count == 0
    assert clients == ["A1"]


def test_with_check_blocks_write_into_another_client(tenants):
    with pytest.raises((DBAPIError, ProgrammingError)):
        with APP.begin() as conn:
            _set_ctx(conn, tenants["a"], tenants["a_client"])
            conn.execute(
                text(
                    "INSERT INTO semantic_memory (consultant_id, client_id, scope, kind, statement) "
                    "VALUES (:c, :cl, 'client', 'fact', 'tentativo cross-client')"
                ),
                {"c": tenants["a"], "cl": tenants["b_client"]},
            )


def test_app_can_enqueue_but_not_read_outbox(tenants):
    with APP.begin() as conn:
        _set_ctx(conn, tenants["a"], tenants["a_client"])
        conn.execute(
            text(
                "INSERT INTO graph_outbox "
                "(aggregate_type, aggregate_id, consultant_id, client_id, op, payload, dedupe_key) "
                "VALUES ('entity', :aid, :c, :cl, 'upsert', '{}'::jsonb, :dk)"
            ),
            {
                "aid": uuid.uuid4(),
                "c": tenants["a"],
                "cl": tenants["a_client"],
                "dk": f"test-{uuid.uuid4()}",
            },
        )
    with pytest.raises((DBAPIError, ProgrammingError)):
        with APP.begin() as conn:
            conn.execute(text("SELECT count(*) FROM graph_outbox"))


def test_guardrail_gate_blocks_active_while_not_clean(tenants):
    with pytest.raises((DBAPIError, ProgrammingError)):
        with APP.begin() as conn:
            _set_ctx(conn, tenants["a"])
            conn.execute(
                text(
                    "INSERT INTO procedural_memory "
                    "(consultant_id, scope, kind, title, body, status, guardrail_status) "
                    "VALUES (:c, 'consultant', 'heuristic', 'X', 'Y', 'active', 'pending')"
                ),
                {"c": tenants["a"]},
            )
