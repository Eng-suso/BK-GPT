"""P5 — ingestione asincrona: kg_ingest_queue + ingest_worker + E2E dal tool.

Skip senza le DSN canonical + NEO4J_PASSWORD. L'E2E dal tool serve anche
WORKSPACE_DATABASE_URL + OPENAI_API_KEY.
"""

from __future__ import annotations

import json
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
    pytest.skip(
        "servono le DSN canonical + NEO4J_PASSWORD", allow_module_level=True
    )

from backend.db import canonical_session  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402
from backend.workers import graph_worker, ingest_worker  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _ctx(conn, consultant, client=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client) if client else ""},
    )


@pytest.fixture()
def scope(monkeypatch):
    """consultant/client/project/process reali + ingest_worker puntato su questo
    consultant (in prod e' `settings.default_consultant_id`, mono-consultant)."""
    c, cl, pj, pr = (uuid.uuid4() for _ in range(4))
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'q')"),
            {"i": c, "e": f"{c}@t.local"},
        )
        _ctx(conn, c)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeQ')"),
            {"i": cl, "c": c},
        )
        conn.execute(
            text("INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"),
            {"i": pj, "cl": cl, "c": c},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Order to Cash')"
            ),
            {"i": pr, "p": pj, "cl": cl, "c": c},
        )
    monkeypatch.setattr(settings, "default_consultant_id", str(c))
    yield {"consultant": str(c), "client": str(cl), "project": str(pj), "process": str(pr)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": c})
    neo4j_store.purge_client(str(cl))


def _queue_rows(scope):
    with canonical_session(scope["consultant"], scope["client"]) as s:
        return s.execute(
            text(
                "SELECT id, status, attempts, last_error, result, payload, "
                "       processed_at, updated_at "
                "FROM kg_ingest_queue WHERE client_id = :cl ORDER BY id"
            ),
            {"cl": scope["client"]},
        ).all()


def _sample_evidence(scope, **over):
    base = dict(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Ufficio crediti", "Direzione amministrativa"],
        relationships=[{
            "source": "Direzione amministrativa", "relation": "autorizza",
            "target": "Ufficio crediti", "confidence": 0.7,
        }],
        source_title="Intervista Finance",
        source_text=(
            "Quando un cliente supera il limite di fido la pratica resta sospesa "
            "finche' la direzione amministrativa non autorizza il rilascio."
        ),
    )
    base.update(over)
    return base


# --- enqueue + worker -------------------------------------------------


def test_enqueue_writes_a_pending_job(scope):
    job_id = canonical.enqueue_evidence(**_sample_evidence(scope))
    rows = _queue_rows(scope)
    assert len(rows) == 1
    row = rows[0]
    assert row.id == job_id
    assert row.status == "pending"
    assert row.attempts == 0
    assert row.payload["source_title"] == "Intervista Finance"
    assert row.payload["consultant_id"] == scope["consultant"]


def test_enqueue_is_client_scoped(scope):
    canonical.enqueue_evidence(**_sample_evidence(scope))
    with canonical_session(scope["consultant"], str(uuid.uuid4())) as s:
        n = s.execute(text("SELECT count(*) FROM kg_ingest_queue")).scalar_one()
    assert n == 0  # RLS: un altro cliente non vede il job


def test_worker_processes_job_and_records_result(scope, wait_projected):
    canonical.enqueue_evidence(**_sample_evidence(scope))

    assert ingest_worker.drain_once() == 1

    row = _queue_rows(scope)[0]
    assert row.status == "done"
    assert row.processed_at is not None
    assert row.result["entities"] == 2
    assert row.result["relationships"] == 1
    assert row.result["chunks"] >= 1

    # il write ha davvero prodotto le entita' + gli outbox
    with canonical_session(scope["consultant"], scope["client"]) as s:
        n_ent = s.execute(
            text("SELECT count(*) FROM kg_entity WHERE client_id = :cl AND status = 'active'"),
            {"cl": scope["client"]},
        ).scalar_one()
    assert n_ent == 2

    # e la catena arriva fino a Neo4j via graph_worker
    driver = neo4j_store.get_driver()

    def _edge() -> bool:
        with driver.session() as neo:
            return neo.run(
                "MATCH (a:Entity)-[r:AUTORIZZA]->(b:Entity) "
                "WHERE a.client_id = $cl RETURN count(r) AS c",
                cl=scope["client"],
            ).single()["c"] > 0

    assert wait_projected(_edge)

    # secondo giro: niente da fare (idempotenza del drain)
    assert ingest_worker.drain_once() == 0


def test_worker_failure_path_retries_then_dead_letters(scope, monkeypatch):
    # write_evidence che solleva -> retry finche' 'failed' (dead-letter)
    def _boom(**_kw):
        raise RuntimeError("estrazione fallita")

    monkeypatch.setattr(canonical, "write_evidence", _boom)
    canonical.enqueue_evidence(**_sample_evidence(scope))

    for expected_attempts in (1, 2, 3, 4):
        assert ingest_worker.drain_once() == 0  # nessun successo
        row = _queue_rows(scope)[0]
        assert row.attempts == expected_attempts
        assert row.status == "pending"
        assert row.last_error

    assert ingest_worker.drain_once() == 0
    row = _queue_rows(scope)[0]
    assert row.attempts == 5
    assert row.status == "failed"  # dead-letter
    assert ingest_worker.queue_stats()["stuck"] == 1


def test_worker_requeues_stuck_processing(scope):
    canonical.enqueue_evidence(**_sample_evidence(scope))
    with canonical_session(scope["consultant"], scope["client"]) as s:
        s.execute(
            text(
                "UPDATE kg_ingest_queue SET status = 'processing', "
                "  updated_at = now() - interval '2 hours' WHERE client_id = :cl"
            ),
            {"cl": scope["client"]},
        )

    assert ingest_worker.drain_once() == 1
    assert _queue_rows(scope)[0].status == "done"


def test_queue_stats_and_prune(scope):
    canonical.enqueue_evidence(**_sample_evidence(scope))
    assert ingest_worker.queue_stats()["pending"] == 1

    ingest_worker.drain_once()
    assert ingest_worker.queue_stats()["pending"] == 0

    with canonical_session(scope["consultant"], scope["client"]) as s:
        s.execute(
            text(
                "UPDATE kg_ingest_queue SET processed_at = now() - interval '30 days' "
                "WHERE client_id = :cl"
            ),
            {"cl": scope["client"]},
        )
    assert ingest_worker.prune(older_than_days=14) == 1
    assert _queue_rows(scope) == []


# --- E2E: tool -> coda -> ingest_worker -> write -> outbox -> Neo4j -> gateway --

_E2E_NEEDED = (settings.workspace_database_url, settings.openai_api_key)


@pytest.mark.skipif(
    not all(_E2E_NEEDED), reason="serve WORKSPACE_DATABASE_URL + OPENAI_API_KEY"
)
def test_evidence_tool_end_to_end(monkeypatch, wait_projected):
    """Il tool reale accoda; ingest_worker + graph_worker completano la catena;
    gateway.graph_retrieve ritrova l'evidenza."""
    from backend import workspace_database
    from backend.memory import gateway
    from backend.toolsets.process_memory import manage_process_evidence

    project_id = f"proj-e2e-{uuid.uuid4().hex[:8]}"
    process_id = f"proc-e2e-{uuid.uuid4().hex[:8]}"
    client_name = f"Acme E2E {uuid.uuid4().hex[:6]}"

    monkeypatch.setattr(
        workspace_database, "get_project",
        lambda pid: {"id": pid, "name": "Progetto E2E", "client": client_name}
        if pid == project_id else None,
    )
    monkeypatch.setattr(
        workspace_database, "get_process",
        lambda pid: {"id": pid, "name": "Order to Cash", "project_id": project_id}
        if pid == process_id else None,
    )

    raw = manage_process_evidence.invoke({
        "operation": "save_episode",
        "project_id": project_id,
        "process_id": process_id,
        "episode_type": "interview",
        "title": "Intervista Finance",
        "raw_content": (
            "Il rilascio della pratica bloccata per sconfinamento del fido "
            "richiede l'autorizzazione della direzione amministrativa."
        ),
        "entities": ["Direzione amministrativa", "Pratica fido"],
        "relationships": [{
            "source": "Direzione amministrativa", "relation": "autorizza",
            "target": "Pratica fido", "confidence": 0.8, "confirmed": True,
        }],
    })
    payload = json.loads(raw.split("\n", 1)[1])["payload"]
    cw = payload["canonical_write"]
    assert cw["queued"] is True
    assert isinstance(cw["job_id"], int)
    client_id = cw["scope"]["client_id"]
    consultant_id = cw["scope"]["consultant_id"]

    try:
        assert ingest_worker.drain_once() >= 1

        def _found() -> bool:
            r = gateway.graph_retrieve(
                consultant_id=consultant_id, client_id=client_id,
                query="chi autorizza il rilascio della pratica bloccata per il fido?",
            )
            rels = {(m["source"], m["relation"], m["target"]) for m in r["matches"]}
            return ("Direzione amministrativa", "AUTORIZZA", "Pratica fido") in rels

        assert wait_projected(_found)
    finally:
        with MIGRATOR.begin() as conn:
            conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": client_id})
        neo4j_store.purge_client(client_id)
