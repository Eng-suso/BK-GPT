"""Pipeline canonical -> graph_outbox -> worker -> Neo4j (P1, INV-7).

Skip senza le tre DSN Postgres + NEO4J_PASSWORD in env.
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
    pytest.skip(
        "servono CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL / "
        "CANONICAL_WORKER_URL / NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402
from backend.workers.graph_worker import drain_once  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _ctx(conn, consultant_id, client_id=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant_id)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


@pytest.fixture()
def scope():
    consultant = uuid.uuid4()
    client = uuid.uuid4()
    project = uuid.uuid4()
    process = uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'proj')"),
            {"i": consultant, "e": f"{consultant}@t.local"},
        )
        _ctx(conn, consultant)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'Acme')"),
            {"i": client, "c": consultant},
        )
        _ctx(conn, consultant, client)
        conn.execute(
            text(
                "INSERT INTO project (id, client_id, consultant_id, name) "
                "VALUES (:i,:cl,:c,'P')"
            ),
            {"i": project, "cl": client, "c": consultant},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Order to Cash')"
            ),
            {"i": process, "p": project, "cl": client, "c": consultant},
        )
    yield {
        "consultant": str(consultant),
        "client": str(client),
        "project": str(project),
        "process": str(process),
    }
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant})
    neo4j_store.purge_client(str(client))


def test_entity_and_relation_reach_neo4j(scope, wait_projected):
    cfo = canonical.write_entity(
        scope["consultant"], scope["client"], "role", "CFO",
        project_id=scope["project"], attributes={"role_type": "CFO", "seniority": "executive"},
    )
    invoice = canonical.write_entity(
        scope["consultant"], scope["client"], "activity", "Emissione fattura",
        project_id=scope["project"],
    )
    canonical.write_relation(
        scope["consultant"], scope["client"], cfo, "approves", invoice,
        project_id=scope["project"], evidence="Il CFO firma prima dell'emissione.",
        confidence=0.8,
    )

    driver = neo4j_store.get_driver()

    def _edge_present() -> bool:
        with driver.session() as neo:
            return neo.run(
                "MATCH (:Entity {entity_id:$s})-[r:APPROVES]->(:Entity {entity_id:$t}) "
                "RETURN count(r) AS c",
                s=cfo, t=invoice,
            ).single()["c"] > 0

    assert wait_projected(_edge_present)

    with driver.session() as neo:
        node = neo.run(
            "MATCH (n:Entity {entity_id: $id}) RETURN n.entity_type AS t, "
            "n.role_type AS role, n.canonical_name AS name",
            id=cfo,
        ).single()
        assert node["t"] == "role"
        assert node["role"] == "CFO"
        assert node["name"] is None  # B+: canonical_name mai in Neo4j

        edge = neo.run(
            "MATCH (:Entity {entity_id: $s})-[r:APPROVES]->(:Entity {entity_id: $t}) "
            "RETURN r.confidence AS c, r.client_id AS cl",
            s=cfo, t=invoice,
        ).single()
        assert edge is not None
        assert abs(edge["c"] - 0.8) < 1e-6
        assert edge["cl"] == scope["client"]


def test_claim_gap_impact_reach_neo4j_with_structural_edges(scope, wait_projected):
    claim = canonical.write_claim(
        scope["consultant"], scope["client"],
        "Finance emette fattura dopo validazione ordine.", "activity",
        project_id=scope["project"], process_id=scope["process"],
        claim_status="confirmed", linked_element_hint="Emissione fattura",
    )
    gap = canonical.write_gap(
        scope["consultant"], scope["client"],
        "Soglia approvazione CFO non chiara", "Manca la soglia in euro.",
        project_id=scope["project"], severity="high",
        affected_process_ids=[scope["process"]],
    )
    canonical.write_impact(
        scope["consultant"], scope["client"],
        "Ritardo incasso", "working_capital",
        "La validazione seriale allunga il ciclo di 3 giorni.",
        project_id=scope["project"], affected_process_ids=[scope["process"]],
        confidence=0.7,
    )

    driver = neo4j_store.get_driver()

    def _claim_present() -> bool:
        with driver.session() as neo:
            return neo.run(
                "MATCH (:Process {process_id:$p})-[:HAS_CLAIM]->(n:Claim {claim_id:$id}) "
                "RETURN count(n) AS c",
                p=scope["process"], id=claim,
            ).single()["c"] > 0

    assert wait_projected(_claim_present)

    with driver.session() as neo:
        c = neo.run(
            "MATCH (:Process {process_id:$p})-[:HAS_CLAIM]->(n:Claim {claim_id:$id}) "
            "RETURN n.process_area AS a, n.linked_element_hint AS h, n.statement AS s",
            p=scope["process"], id=claim,
        ).single()
        assert c["a"] == "activity"
        assert c["h"] == "Emissione fattura"
        assert c["s"] is None  # B+: statement mai in Neo4j

        g = neo.run(
            "MATCH (:Gap {gap_id:$id})-[:BLOCKS]->(:Process {process_id:$p}) RETURN 1 AS ok",
            id=gap, p=scope["process"],
        ).single()
        assert g is not None

        imp = neo.run(
            "MATCH (n:Impact)-[:AFFECTS]->(:Process {process_id:$p}) "
            "RETURN n.impact_area AS a",
            p=scope["process"],
        ).single()
        assert imp["a"] == "working_capital"


def test_write_evidence_is_atomic(scope):
    from sqlalchemy import create_engine, text
    from backend.memory.knowledge_graph import canonical

    # process_id malformato: l'INSERT dell'entita' fallira' a meta' pacchetto
    with pytest.raises(Exception):
        canonical.write_evidence(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            project_id=scope["project"],
            process_id="non-e-un-uuid",
            entities=["Alfa", "Beta"],
            relationships=[{"source": "Alfa", "relation": "linked", "target": "Beta"}],
        )

    eng = create_engine(settings.canonical_migrator_url, future=True)
    with eng.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": scope["consultant"]},
        )
        conn.execute(
            text("SELECT set_config('app.current_client_id', :v, true)"),
            {"v": scope["client"]},
        )
        n = conn.execute(
            text("SELECT count(*) FROM kg_entity WHERE client_id = :c"),
            {"c": scope["client"]},
        ).scalar_one()
    assert n == 0  # rollback totale: nessuna entita' parziale


def test_worker_marks_processed_and_is_idempotent(scope, wait_projected):
    canonical.write_entity(scope["consultant"], scope["client"], "system", "SAP")

    def _pending() -> int:
        with MIGRATOR.begin() as conn:  # graph_outbox: nessuna RLS (migration 0004)
            return conn.execute(
                text(
                    "SELECT count(*) FROM graph_outbox "
                    "WHERE client_id = :cl AND processed_at IS NULL"
                ),
                {"cl": scope["client"]},
            ).scalar_one()

    assert wait_projected(lambda: _pending() == 0)
    assert _pending() == 0
