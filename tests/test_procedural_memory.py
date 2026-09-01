"""P7.1 — playbook appresi: candidate -> guardrail -> active -> retrieval.

Copre INV-11 (tassonomia procedural), INV-12 (playbook appresi = Postgres SoT,
accanto alle repo-skill), INV-13 (due scope + generalizzazione, non copia) e il
gate DB sul guardrail (`procedural_guardrail_gate`, migration 0003).

Skip senza CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

from backend.memory import canonical_memory, gateway  # noqa: E402

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
def tenant():
    consultant_id = uuid.uuid4()
    client_a = uuid.uuid4()
    client_b = uuid.uuid4()
    client_name = f"Rossi Manifattura {uuid.uuid4().hex[:6]}"

    with MIGRATOR.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consultant (id, email, display_name) "
                "VALUES (:i, :e, :n)"
            ),
            {"i": consultant_id, "e": f"pb-{consultant_id.hex[:8]}@t.local", "n": "pb-cons"},
        )
        _ctx(conn, consultant_id)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i, :c, :n)"),
            {"i": client_a, "c": consultant_id, "n": client_name},
        )
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i, :c, 'Altro Cliente')"),
            {"i": client_b, "c": consultant_id},
        )

    yield {
        "consultant": str(consultant_id),
        "client_a": str(client_a),
        "client_b": str(client_b),
        "client_name": client_name,
    }

    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant_id})


def test_guardrail_blocks_pii_then_clean_body_promotes(tenant):
    consultant = tenant["consultant"]

    dirty = canonical_memory.write_procedural_candidate(
        consultant,
        kind="playbook",
        title="Kickoff discovery di processo",
        applies_when="quando parte una discovery di processo con un nuovo cliente",
        body=(
            "Allinea lo sponsor scrivendo a mario.rossi@example.com e chiamando "
            "il +39 340 111 2233 prima del kickoff."
        ),
        scope="consultant",
    )
    flagged = canonical_memory.promote_procedural(dirty, consultant_id=consultant)
    assert flagged["status"] == "guardrail_flagged"
    assert any(f["kind"] == "pii" for f in flagged["findings"])

    with MIGRATOR.begin() as conn:
        _ctx(conn, consultant)
        row = conn.execute(
            text("SELECT status, guardrail_status FROM procedural_memory WHERE id = :i"),
            {"i": dirty},
        ).one()
    assert row.status == "candidate"
    assert row.guardrail_status == "flagged"

    clean = canonical_memory.write_procedural_candidate(
        consultant,
        kind="playbook",
        title="Kickoff discovery di processo",
        applies_when="quando parte una discovery di processo con un nuovo cliente",
        body=(
            "Allinea lo sponsor sugli obiettivi, conferma i vincoli di tempo e "
            "concorda i partecipanti alle interviste prima del kickoff."
        ),
        scope="consultant",
    )
    promoted = canonical_memory.promote_procedural(clean, consultant_id=consultant)
    assert promoted["status"] == "promoted"

    hit = gateway.procedural_retrieve(
        consultant_id=consultant,
        task_text="stiamo per partire con una discovery di processo",
    )
    assert "Kickoff discovery di processo" in [p["title"] for p in hit["playbooks"]]


def test_consultant_scope_flags_leftover_client_name(tenant):
    consultant = tenant["consultant"]

    candidate = canonical_memory.write_procedural_candidate(
        consultant,
        kind="heuristic",
        title="Gestione stakeholder tecnici",
        body=f"Con {tenant['client_name']} conviene sentire prima le operations.",
        scope="consultant",
    )
    flagged = canonical_memory.promote_procedural(candidate, consultant_id=consultant)
    assert flagged["status"] == "guardrail_flagged"
    assert any(f["kind"] == "client_reference" for f in flagged["findings"])


def test_client_scoped_playbook_is_isolated(tenant):
    consultant = tenant["consultant"]
    client_a = tenant["client_a"]
    client_b = tenant["client_b"]

    candidate = canonical_memory.write_procedural_candidate(
        consultant,
        kind="checklist",
        title="Chiusura sprint di delivery",
        body="Verifica i deliverable, aggiorna il registro rischi, prepara la nota di stato.",
        scope="client",
        client_id=client_a,
    )
    assert (
        canonical_memory.promote_procedural(
            candidate, consultant_id=consultant, client_id=client_a
        )["status"]
        == "promoted"
    )

    in_a = gateway.procedural_retrieve(
        consultant_id=consultant, client_id=client_a, task_text="chiusura sprint deliverable"
    )
    assert "Chiusura sprint di delivery" in [p["title"] for p in in_a["playbooks"]]

    in_b = gateway.procedural_retrieve(
        consultant_id=consultant, client_id=client_b, task_text="chiusura sprint deliverable"
    )
    assert "Chiusura sprint di delivery" not in [p["title"] for p in in_b["playbooks"]]

    consultant_only = gateway.procedural_retrieve(
        consultant_id=consultant, task_text="chiusura sprint deliverable"
    )
    assert "Chiusura sprint di delivery" not in [p["title"] for p in consultant_only["playbooks"]]


def test_consultant_playbook_visible_in_every_client(tenant):
    consultant = tenant["consultant"]
    client_a = tenant["client_a"]

    candidate = canonical_memory.write_procedural_candidate(
        consultant,
        kind="playbook",
        title="Sintesi delle evidenze",
        body="Raggruppa le evidenze per tema, marca le contraddizioni, elenca le domande aperte.",
        scope="consultant",
    )
    assert (
        canonical_memory.promote_procedural(candidate, consultant_id=consultant)["status"]
        == "promoted"
    )

    seen = gateway.procedural_retrieve(
        consultant_id=consultant, client_id=client_a, task_text="sintesi delle evidenze per tema"
    )
    assert "Sintesi delle evidenze" in [p["title"] for p in seen["playbooks"]]


def test_one_active_version_per_lineage(tenant):
    consultant = tenant["consultant"]

    v1 = canonical_memory.write_procedural_candidate(
        consultant,
        kind="playbook",
        title="Revisione modello AS-IS v1",
        body="Passi base per rivedere il modello AS-IS con lo sponsor.",
        scope="consultant",
    )
    assert canonical_memory.promote_procedural(v1, consultant_id=consultant)["status"] == "promoted"

    v2 = canonical_memory.write_procedural_candidate(
        consultant,
        kind="playbook",
        title="Revisione modello AS-IS v2",
        body="Passi rivisti per rivedere il modello AS-IS, con checklist di validazione.",
        scope="consultant",
        supersedes_id=v1,
    )
    assert canonical_memory.promote_procedural(v2, consultant_id=consultant)["status"] == "promoted"

    with MIGRATOR.begin() as conn:
        _ctx(conn, consultant)
        rows = conn.execute(
            text(
                "SELECT status FROM procedural_memory "
                "WHERE id IN (:a, :b) ORDER BY version"
            ),
            {"a": v1, "b": v2},
        ).all()
    assert [r.status for r in rows] == ["deprecated", "active"]
