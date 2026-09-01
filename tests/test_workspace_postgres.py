"""Lo stato operativo (workspace / chat / indice episodico) gira su Postgres.

Nessun fallback SQLite: senza `WORKSPACE_DATABASE_URL` l'app non parte, quindi
questi test o girano su Postgres o si skippano.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

from backend import database as chat_db  # noqa: E402
from backend import workspace_database as wd  # noqa: E402
from backend.memory.episodic import episodic_store  # noqa: E402
from backend.security import reset_current_tenant_id, set_current_tenant_id  # noqa: E402


def test_engines_are_postgres():
    assert wd.workspace_engine.dialect.name == "postgresql"
    assert chat_db.engine.dialect.name == "postgresql"
    assert episodic_store.engine.dialect.name == "postgresql"


def test_workspace_round_trip_and_tenant_isolation():
    tenant_a = f"t-{uuid.uuid4().hex[:8]}"
    tenant_b = f"t-{uuid.uuid4().hex[:8]}"

    tok = set_current_tenant_id(tenant_a)
    try:
        client = wd.create_client(name="Acme PG")
        project = wd.create_project(client_id=client["id"], name="Mapping PG")
        process = wd.create_process(project_id=project["id"], name="Order to Cash PG")
        assert wd.get_process(process["id"])["name"] == "Order to Cash PG"
        assert project["id"] in {p["id"] for p in wd.list_projects()}
    finally:
        reset_current_tenant_id(tok)

    tok = set_current_tenant_id(tenant_b)
    try:
        # tenant B non vede i progetti di A
        assert project["id"] not in {p["id"] for p in wd.list_projects()}
    finally:
        reset_current_tenant_id(tok)

    tok = set_current_tenant_id(tenant_a)
    try:
        wd.reset_workspace()
        assert wd.list_projects() == []
    finally:
        reset_current_tenant_id(tok)


def test_langgraph_checkpointer_is_postgres():
    from backend.agent_checkpoint import get_checkpointer

    saver = get_checkpointer()
    assert type(saver).__name__ == "PostgresSaver"
    # setup() e' idempotente: una seconda chiamata non deve sollevare
    saver.setup()
    cfg = {"configurable": {"thread_id": f"ck-{uuid.uuid4().hex[:8]}"}}
    assert saver.get(cfg) is None  # thread nuovo, nessun checkpoint


def test_chat_history_round_trip_on_postgres():
    tenant = f"t-{uuid.uuid4().hex[:8]}"
    tok = set_current_tenant_id(tenant)
    try:
        thread = f"thr-{uuid.uuid4().hex[:8]}"
        chat_db.append_chat_message(thread, "user", "ciao")
        chat_db.append_chat_message(thread, "assistant", "ciao a te")
        session = chat_db.get_chat_session(thread)
        assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
        chat_db.delete_chat_session(thread)
        assert chat_db.get_chat_session(thread) is None
    finally:
        reset_current_tenant_id(tok)
