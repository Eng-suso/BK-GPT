"""Lo stato della proiezione per cliente, sul database vero (P1.1b).

Watermark, versione del projector e `CORRUPT` vivono in
`graph_projection_state`: qui si prova che le scritture fanno quello che il
loro nome promette, e che i ruoli vedono solo quello che devono.

Skip senza le DSN canonical (migrator e worker).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from backend.settings import settings

if not (settings.canonical_migrator_url and settings.canonical_worker_url and settings.canonical_database_url):
    pytest.skip(
        "servono CANONICAL_MIGRATOR_URL / CANONICAL_WORKER_URL / CANONICAL_DATABASE_URL",
        allow_module_level=True,
    )

from backend.memory.knowledge_graph import projection_state  # noqa: E402
from backend.memory.knowledge_graph.projector import PROJECTOR_VERSION  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)
WORKER = create_engine(settings.canonical_worker_url, future=True)
APP = create_engine(settings.canonical_database_url, future=True)


@pytest.fixture()
def client_id():
    value = str(uuid.uuid4())
    yield value
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("DELETE FROM graph_projection_state WHERE client_id = CAST(:cl AS uuid)"),
            {"cl": value},
        )


def _read(client_id: str) -> projection_state.ProjectionState | None:
    with WORKER.begin() as conn:
        return projection_state.read(conn, client_id)


def test_a_client_never_projected_has_no_state(client_id):
    assert _read(client_id) is None


def test_the_watermark_only_moves_forward(client_id):
    with WORKER.begin() as conn:
        projection_state.advance_watermark(conn, client_id, 40)
        projection_state.advance_watermark(conn, client_id, 12)

    state = _read(client_id)
    assert state is not None
    assert state.watermark == 40
    assert state.projector_version == PROJECTOR_VERSION


def test_a_new_projector_does_not_relabel_an_old_graph(client_id):
    # Il grafo scritto in parte da un projector vecchio resta di quel projector
    # finche' una ricostruzione completa non lo riscrive tutto.
    with MIGRATOR.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO graph_projection_state (client_id, watermark, projector_version) "
                "VALUES (CAST(:cl AS uuid), 5, 'vecchio')"
            ),
            {"cl": client_id},
        )
    with WORKER.begin() as conn:
        projection_state.advance_watermark(conn, client_id, 9)

    state = _read(client_id)
    assert state is not None
    assert (state.watermark, state.projector_version) == (9, "vecchio")

    with MIGRATOR.begin() as conn:
        projection_state.mark_verified(conn, client_id, rebuilt=True)

    state = _read(client_id)
    assert state is not None
    assert state.projector_version == PROJECTOR_VERSION
    assert state.watermark == 9


def test_a_failed_reconciliation_marks_the_graph_corrupt_until_a_clean_one(client_id):
    with MIGRATOR.begin() as conn:
        projection_state.mark_corrupt(conn, client_id, "missing_edges=3")

    state = _read(client_id)
    assert state is not None
    assert state.corrupt
    assert state.corrupt_reason == "missing_edges=3"

    with MIGRATOR.begin() as conn:
        projection_state.mark_verified(conn, client_id, rebuilt=False)

    state = _read(client_id)
    assert state is not None
    assert not state.corrupt
    assert state.corrupt_reason is None
    assert state.verified_at is not None


def test_the_app_role_cannot_read_the_state(client_id):
    with WORKER.begin() as conn:
        projection_state.advance_watermark(conn, client_id, 1)

    with pytest.raises(ProgrammingError), APP.begin() as conn:
        conn.execute(text("SELECT * FROM graph_projection_state"))


def _enqueue(client_id: str | None) -> int:
    with MIGRATOR.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO graph_outbox "
                "(aggregate_type, aggregate_id, consultant_id, client_id, op, payload, dedupe_key) "
                "VALUES ('entity', CAST(:agg AS uuid), CAST(:cons AS uuid), CAST(:cl AS uuid), "
                "        'upsert', CAST(:payload AS jsonb), :key) RETURNING id"
            ),
            {
                "agg": str(uuid.uuid4()),
                "cons": str(uuid.uuid4()),
                "cl": client_id,
                "payload": '{"kind": "node"}',
                "key": f"test-projection-state-{uuid.uuid4()}",
            },
        ).scalar_one()


def _drop(outbox_id: int) -> None:
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM graph_outbox WHERE id = :id"), {"id": outbox_id})


def test_an_applied_row_advances_its_client_watermark(client_id):
    from backend.workers import graph_worker

    outbox_id = _enqueue(client_id)
    try:
        with WORKER.begin() as conn:
            graph_worker._mark_applied(conn, outbox_id, client_id)
            processed = conn.execute(
                text("SELECT processed_at FROM graph_outbox WHERE id = :id"), {"id": outbox_id}
            ).scalar_one()

        assert processed is not None
        state = _read(client_id)
        assert state is not None
        assert state.watermark == outbox_id
    finally:
        _drop(outbox_id)


def test_a_row_without_a_client_leaves_no_state():
    from backend.workers import graph_worker

    outbox_id = _enqueue(None)
    try:
        count = text("SELECT count(*) FROM graph_projection_state")
        with WORKER.begin() as conn:
            before = conn.execute(count).scalar_one()
            graph_worker._mark_applied(conn, outbox_id, None)
            after = conn.execute(count).scalar_one()
            processed = conn.execute(
                text("SELECT processed_at FROM graph_outbox WHERE id = :id"), {"id": outbox_id}
            ).scalar_one()

        assert processed is not None
        assert after == before
    finally:
        _drop(outbox_id)


def _diff(**counts):
    from backend.memory.knowledge_graph.reproject import GraphDiff

    lists = {
        name: [("Entity", f"id-{i}") for i in range(counts.get(name, 0))]
        for name in ("missing_nodes", "extra_nodes", "duplicate_nodes", "drifted_nodes")
    }
    edge = ("REL", ("Entity", "a"), ("Entity", "b"))
    lists.update(
        {
            name: [edge] * counts.get(name, 0)
            for name in ("missing_edges", "extra_edges", "duplicate_edges", "drifted_edges")
        }
    )
    return GraphDiff(**lists, expected_nodes=10, expected_edges=10)


def _run_script(monkeypatch, client_id: str, *args: str) -> int:
    from scripts import kg_reproject as script

    monkeypatch.setattr("sys.argv", ["kg_reproject", "--client", client_id, "--consultant", str(uuid.uuid4()), *args])
    return script.main()


def test_a_reconciliation_that_finds_differences_marks_the_graph_corrupt(monkeypatch, client_id):
    from backend.memory.knowledge_graph import reproject

    monkeypatch.setattr(reproject, "diff", lambda *_a: _diff(missing_edges=3, extra_nodes=1))

    assert _run_script(monkeypatch, client_id) == 1

    state = _read(client_id)
    assert state is not None and state.corrupt
    assert state.corrupt_reason == "extra_nodes=1, missing_edges=3"


def test_a_clean_reconciliation_clears_the_mark(monkeypatch, client_id):
    from backend.memory.knowledge_graph import reproject

    with MIGRATOR.begin() as conn:
        projection_state.mark_corrupt(conn, client_id, "missing_edges=3")
    monkeypatch.setattr(reproject, "diff", lambda *_a: _diff())

    assert _run_script(monkeypatch, client_id) == 0

    state = _read(client_id)
    assert state is not None and not state.corrupt
    assert state.verified_at is not None


def test_a_rebuild_brings_the_projector_version_forward(monkeypatch, client_id):
    from backend.memory.knowledge_graph import reproject

    with MIGRATOR.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO graph_projection_state (client_id, watermark, projector_version) "
                "VALUES (CAST(:cl AS uuid), 7, 'vecchio')"
            ),
            {"cl": client_id},
        )
    report = reproject.ApplyReport(
        before=_diff(drifted_nodes=2), after=_diff(), deleted_nodes=0, deleted_edges=0,
        applied_nodes=10, applied_edges=10,
    )
    monkeypatch.setattr(reproject, "apply", lambda *_a: report)

    assert _run_script(monkeypatch, client_id, "--apply") == 0

    state = _read(client_id)
    assert state is not None
    assert (state.projector_version, state.watermark, state.corrupt) == (PROJECTOR_VERSION, 7, False)


def test_a_rebuild_that_leaves_differences_is_corrupt(monkeypatch, client_id):
    from backend.memory.knowledge_graph import reproject

    report = reproject.ApplyReport(
        before=_diff(missing_nodes=1), after=_diff(missing_nodes=1), deleted_nodes=0,
        deleted_edges=0, applied_nodes=9, applied_edges=10,
    )
    monkeypatch.setattr(reproject, "apply", lambda *_a: report)

    assert _run_script(monkeypatch, client_id, "--apply") == 1

    state = _read(client_id)
    assert state is not None and state.corrupt
