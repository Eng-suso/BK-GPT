"""P7.2 — pattern extraction: episodi ricorrenti -> playbook candidate.

Copre: `extract_playbook_from_episodes` legge gli episodi client-scoped, salva un
candidate scope='client' con `derived_from` = gli id episodi, ed e' idempotente
sullo stesso set. L'LLM di estrazione e' sostituito da un fake (test ermetico).

Skip senza CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

from backend import workspace_database  # noqa: E402
from backend.memory import canonical_memory  # noqa: E402
from backend.memory import scope as canonical_scope  # noqa: E402
from backend.memory.procedural.extraction import ExtractedPlaybook  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _ctx(conn, consultant_id, client_id: str = "") -> None:
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant_id)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


@pytest.fixture()
def project_scope(monkeypatch):
    workspace_project_id = f"proj-ext-{uuid.uuid4().hex[:8]}"
    client_name = f"Cliente Extract {uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(
        workspace_database,
        "get_project",
        lambda p: {"id": p, "name": "Progetto Extract", "client": client_name}
        if p == workspace_project_id
        else None,
    )
    monkeypatch.setattr(workspace_database, "get_process", lambda p: None)

    yield workspace_project_id

    client_ws = f"client:{canonical_scope._slug(client_name)}"
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM client WHERE workspace_id = :w"), {"w": client_ws})


def test_extract_creates_candidate_then_dedups(project_scope, monkeypatch):
    consultant = settings.default_consultant_id
    resolved = canonical_scope.resolve(project_scope)
    client_id, canonical_project_id = resolved.client_id, resolved.project_id

    episode_ids: list[str] = []
    with MIGRATOR.begin() as conn:
        _ctx(conn, consultant, client_id)
        for i in range(3):
            row = conn.execute(
                text(
                    "INSERT INTO episodic_memory "
                    "(consultant_id, client_id, project_id, scope, episode_type, title, summary) "
                    "VALUES (:c, :cl, :p, 'client', 'note', :t, :s) RETURNING id"
                ),
                {
                    "c": consultant,
                    "cl": client_id,
                    "p": canonical_project_id,
                    "t": f"Nota discovery {i}",
                    "s": f"Il team ha ripetuto il passo {i} prima di validare.",
                },
            ).one()
            episode_ids.append(str(row.id))

    fake = ExtractedPlaybook(
        kind="playbook",
        title="Validazione a valle della discovery",
        applies_when="dopo ogni ciclo di interviste",
        body="Passi: raccogli, confronta, valida con lo sponsor. Evita di modellare senza conferma.",
        confidence=0.5,
    )
    monkeypatch.setattr(
        "backend.memory.procedural.extraction.extract_playbook_from_episodes",
        lambda episodes, **kwargs: fake,
    )

    from backend.toolsets.memory import extract_playbook_from_episodes as tool

    out1 = tool.invoke({"project": project_scope, "limit": 5})
    payload1 = json.loads(out1.split("\n", 1)[1])
    assert payload1["status"] == "saved"
    new_id = payload1["payload"]["playbook_id"]
    assert set(payload1["payload"]["derived_from"]) == set(episode_ids)

    detail = canonical_memory.get_procedural(
        new_id, consultant_id=consultant, client_id=client_id
    )
    assert detail["status"] == "candidate"
    assert detail["scope"] == "client"
    assert sorted(str(x) for x in detail["derived_from"]) == sorted(episode_ids)

    out2 = tool.invoke({"project": project_scope, "limit": 5})
    payload2 = json.loads(out2.split("\n", 1)[1])
    assert payload2["status"] == "noop"
    assert payload2["payload"]["playbook_id"] == new_id

    # il candidate client-scoped si promuove via il tool passando project
    from backend.toolsets.memory import manage_consultant_playbook as playbook_tool

    promoted = json.loads(
        playbook_tool.invoke(
            {"operation": "promote", "project": project_scope, "playbook_id": new_id}
        ).split("\n", 1)[1]
    )
    assert promoted["status"] == "activated"

    seen = json.loads(
        playbook_tool.invoke(
            {"operation": "list", "project": project_scope, "query": fake.title}
        ).split("\n", 1)[1]
    )
    assert new_id in [p["id"] for p in seen["payload"]["playbooks"]]


def test_extract_needs_at_least_two_episodes(project_scope, monkeypatch):
    consultant = settings.default_consultant_id
    resolved = canonical_scope.resolve(project_scope)

    with MIGRATOR.begin() as conn:
        _ctx(conn, consultant, resolved.client_id)
        conn.execute(
            text(
                "INSERT INTO episodic_memory "
                "(consultant_id, client_id, project_id, scope, episode_type, title, summary) "
                "VALUES (:c, :cl, :p, 'client', 'note', 'Solo una', 'Un episodio isolato.')"
            ),
            {"c": consultant, "cl": resolved.client_id, "p": resolved.project_id},
        )

    monkeypatch.setattr(
        "backend.memory.procedural.extraction.extract_playbook_from_episodes",
        lambda episodes, **kwargs: pytest.fail("non deve chiamare l'estrattore"),
    )

    from backend.toolsets.memory import extract_playbook_from_episodes as tool

    out = tool.invoke({"project": project_scope, "limit": 5})
    assert json.loads(out.split("\n", 1)[1])["status"] == "empty"
