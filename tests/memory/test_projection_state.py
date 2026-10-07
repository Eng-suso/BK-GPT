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
