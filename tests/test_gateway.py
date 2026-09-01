"""Gateway di lettura: graph_retrieve legge Neo4j + idrata da Postgres, scoped.

Skip senza le tre DSN Postgres + NEO4J_PASSWORD.
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
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip("servono le DSN canonical + NEO4J_PASSWORD", allow_module_level=True)

from backend.memory import gateway  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402
from backend.workers.graph_worker import drain_once  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _ctx(conn, cid, clid=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"), {"v": str(cid)}
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(clid) if clid else ""},
    )


@pytest.fixture()
def scope():
    c, cl, pj, pr = (uuid.uuid4() for _ in range(4))
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'g')"),
            {"i": c, "e": f"{c}@t.local"},
        )
        _ctx(conn, c)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeGW')"),
            {"i": cl, "c": c},
        )
        conn.execute(
            text(
                "INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"
            ),
            {"i": pj, "cl": cl, "c": c},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Order to Cash')"
            ),
            {"i": pr, "p": pj, "cl": cl, "c": c},
        )
    yield {"consultant": str(c), "client": str(cl), "project": str(pj), "process": str(pr)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": c})
    neo4j_store.purge_client(str(cl))


def test_graph_retrieve_returns_hydrated_triples(scope):
    canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["CFO", "Emissione fattura"],
        relationships=[
            {"source": "CFO", "relation": "approves", "target": "Emissione fattura",
             "confidence": 0.8, "confirmed": True},
        ],
        claims=[
            {"statement": "Finance emette fattura dopo validazione ordine.",
             "process_area": "activity", "claim_status": "confirmed"},
        ],
    )
    assert drain_once() >= 3

    result = gateway.graph_retrieve(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        entity_names=["CFO"],
        process_id=scope["process"],
    )
    assert result["status"] == "ok"
    rels = {(m["source"], m["relation"], m["target"]) for m in result["matches"]}
    assert ("CFO", "APPROVES", "Emissione fattura") in rels
    # nomi idratati da Postgres, non id opachi
    assert all(not _looks_like_uuid(m["source"]) for m in result["matches"])


def test_graph_retrieve_is_client_scoped(scope):
    canonical.write_evidence(
        consultant_id=scope["consultant"], client_id=scope["client"],
        project_id=scope["project"], process_id=scope["process"],
        entities=["Segreto A", "Segreto B"],
        relationships=[{"source": "Segreto A", "relation": "linked", "target": "Segreto B"}],
    )
    drain_once()

    other_client = str(uuid.uuid4())
    result = gateway.graph_retrieve(
        consultant_id=scope["consultant"],
        client_id=other_client,          # cliente diverso
        entity_names=["Segreto A"],
    )
    # nessun seed nel client sbagliato -> niente match
    assert result["matches"] == []


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False
