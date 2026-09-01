"""P7.4 — feedback loop: usage + outcome sui playbook appresi.

`record_playbook_usage` conta le iniezioni nel prompt; `record_playbook_outcome`
aggiorna la confidence con una media mobile e auto-depreca un playbook con
confidence bassa e troppi esiti negativi.

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
from backend.memory.procedural import playbook_context  # noqa: E402

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
def consultant():
    consultant_id = uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i, :e, :n)"),
            {"i": consultant_id, "e": f"fb-{consultant_id.hex[:8]}@t.local", "n": "fb-cons"},
        )
    yield str(consultant_id)
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant_id})


def _active_playbook(consultant_id: str, title: str, *, confidence: float = 0.5) -> str:
    pid = canonical_memory.write_procedural_candidate(
        consultant_id,
        kind="playbook",
        title=title,
        body="Passi generici della revisione con lo sponsor.",
        scope="consultant",
        confidence=confidence,
    )
    assert canonical_memory.promote_procedural(pid, consultant_id=consultant_id)["status"] == "promoted"
    return pid


def test_record_usage_counts_only_active(consultant):
    active = _active_playbook(consultant, "Playbook attivo")
    candidate = canonical_memory.write_procedural_candidate(
        consultant, kind="playbook", title="Solo candidate",
        body="Testo.", scope="consultant",
    )

    touched = canonical_memory.record_playbook_usage(
        consultant, playbook_ids=[active, candidate]
    )
    assert touched == 1

    with MIGRATOR.begin() as conn:
        _ctx(conn, consultant)
        rows = dict(
            conn.execute(
                text("SELECT id, used_count FROM procedural_memory WHERE id IN (:a, :c)"),
                {"a": active, "c": candidate},
            ).all()
        )
    assert rows[uuid.UUID(active)] == 1
    assert rows[uuid.UUID(candidate)] == 0


def test_positive_outcomes_raise_confidence(consultant):
    playbook = _active_playbook(consultant, "Playbook che funziona", confidence=0.3)

    worked = canonical_memory.record_playbook_outcome(
        playbook, "worked", consultant_id=consultant
    )
    assert worked["status"] == "recorded"
    # ratio smussato: (1 + 0 + 0.5) / (1 + 0 + 0 + 1)
    assert worked["confidence"] == pytest.approx(0.75)
    assert worked["auto_deprecated"] is False

    partial = canonical_memory.record_playbook_outcome(
        playbook, "partial", consultant_id=consultant
    )
    # (1 + 0.5 + 0.5) / (1 + 1 + 0 + 1)
    assert partial["confidence"] == pytest.approx(0.6667, abs=1e-3)


def test_repeated_failures_auto_deprecate(consultant):
    playbook = _active_playbook(consultant, "Playbook da bocciare", confidence=0.5)

    results = [
        canonical_memory.record_playbook_outcome(playbook, "didn't_work", consultant_id=consultant)
        for _ in range(3)
    ]
    # confidence sotto soglia + 3 fallimenti -> auto-deprecato una volta sola
    assert [r["auto_deprecated"] for r in results] == [False, False, True]

    detail = canonical_memory.get_procedural(playbook, consultant_id=consultant)
    assert detail["status"] == "deprecated"
    assert detail["outcome_failed"] == 3
    assert detail["outcome_worked"] == 0


def test_bad_outcome_is_rejected(consultant):
    playbook = _active_playbook(consultant, "Playbook ok")
    result = canonical_memory.record_playbook_outcome(
        playbook, "meh", consultant_id=consultant
    )
    assert result["status"] == "bad_outcome"


def test_build_playbook_context_records_usage(consultant, monkeypatch):
    playbook = _active_playbook(consultant, "Revisione modello AS-IS con lo sponsor")
    monkeypatch.setattr(playbook_context.settings, "default_consultant_id", consultant)

    block = playbook_context.build_playbook_context(
        "come conviene rivedere il modello AS-IS con lo sponsor"
    )
    assert "Revisione modello AS-IS" in block

    detail = canonical_memory.get_procedural(playbook, consultant_id=consultant)
    assert detail["used_count"] == 1
