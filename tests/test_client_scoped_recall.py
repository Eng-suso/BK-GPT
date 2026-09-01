"""INV-13: la memoria episodica di un progetto e' client-scoped.

Un episodio salvato per un progetto finisce in Mem0 con `client_id` nei
metadata e nella riga canonical con scope 'client'. Il gateway lo restituisce
nel contesto di quel cliente, non di un altro.

Skip senza le DSN canonical + MEM0_DATABASE_URL + OPENAI_API_KEY.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.mem0_database_url,
    settings.openai_api_key,
)
if not all(_NEEDED):
    pytest.skip(
        "servono le DSN canonical + MEM0_DATABASE_URL + OPENAI_API_KEY",
        allow_module_level=True,
    )

from backend import workspace_database  # noqa: E402
from backend.memory import gateway, mem0_client  # noqa: E402
from backend.memory import scope as canonical_scope  # noqa: E402
from backend.memory.episodic import episodic_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


@pytest.fixture()
def project(monkeypatch):
    pid = f"proj-cs-{uuid.uuid4().hex[:8]}"
    client_name = f"Cliente Scope {uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(
        workspace_database, "get_project",
        lambda p: {"id": p, "name": "Progetto Scope", "client": client_name}
        if p == pid else None,
    )
    yield pid
    client_ws = f"client:{canonical_scope._slug(client_name)}"
    with MIGRATOR.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM client WHERE workspace_id = :w"), {"w": client_ws}
        ).first()
        if not row:
            return
        client_id = row[0]
        mem_ids = conn.execute(
            text(
                "SELECT mem0_memory_id FROM mem0_projection_log "
                "WHERE client_id = :c AND mem0_memory_id IS NOT NULL"
            ),
            {"c": client_id},
        ).scalars().all()
        conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": client_id})
    mem = mem0_client.get_memory()
    for mid in mem_ids:
        try:
            mem.delete(memory_id=str(mid))
        except Exception:
            pass


def test_episode_recall_is_client_scoped(project):
    marker = "Vendor" + uuid.uuid4().hex[:6]
    episodic_store.save_episode_memory(
        episode_type="interview",
        title=f"Colloquio con {marker}",
        raw_content=(
            f"Il fornitore {marker} consegna i materiali critici con 6 settimane "
            f"di anticipo e chiede un acconto del 30 percento alla conferma ordine."
        ),
        summary=f"Termini di fornitura di {marker}.",
        project=project,
    )

    client_id = canonical_scope.resolve_client_id(project)
    assert client_id is not None

    # riga canonical: scope 'client'
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": settings.default_consultant_id},
        )
        conn.execute(
            text("SELECT set_config('app.current_client_id', :v, true)"),
            {"v": client_id},
        )
        row = conn.execute(
            text(
                "SELECT scope, client_id FROM episodic_memory "
                "WHERE title = :t ORDER BY created_at DESC LIMIT 1"
            ),
            {"t": f"Colloquio con {marker}"},
        ).first()
    assert row is not None
    assert row.scope == "client"
    assert str(row.client_id) == client_id

    # recall nel cliente giusto -> trovato, marcato client_scoped
    hit = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        client_id=client_id,
        query=f"termini di fornitura del vendor {marker}",
        limit=10,
    )
    ours = [m for m in hit["matches"] if marker in (m["memory"] or "")]
    assert ours, "l'episodio deve tornare nel contesto del suo cliente"
    assert all(m["client_scoped"] for m in ours)

    for m in ours:
        if m["memory_id"]:
            try:
                mem0_client.get_memory().delete(memory_id=m["memory_id"])
            except Exception:
                pass

    # recall in un altro cliente -> niente
    other = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        client_id=str(uuid.uuid4()),
        query=f"termini di fornitura del vendor {marker}",
        limit=10,
    )
    assert not [m for m in other["matches"] if marker in (m["memory"] or "")]
