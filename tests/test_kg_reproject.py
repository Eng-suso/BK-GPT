"""GR-01 / GR-12 — la proiezione Neo4j si ricostruisce da Postgres, e se e'
indietro `graph_retrieve` lo dice (docs/graph-rag-remediation.md).

Il test che conta e' il primo: un grafo scritto dal write path vero
(`canonical.write_*` -> outbox -> worker) confrontato con lo stesso grafo
ricostruito da `reproject` deve risultare identico. Se un domani il write path
cambia forma e `reproject` no, e' qui che si rompe - non in produzione il giorno
della riparazione.

Servono le DSN canonical + NEO4J_PASSWORD (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import random
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

from backend.memory import gateway  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store, reproject  # noqa: E402
from backend.workers.graph_worker import drain_once  # noqa: E402
from scripts import kg_reproject  # noqa: E402

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


def _drain_all() -> None:
    for _ in range(20):
        if drain_once() == 0:
            return


@pytest.fixture()
def world():
    consultant, client, project, process = (uuid.uuid4() for _ in range(4))
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'reproj')"),
            {"i": consultant, "e": f"{consultant}@t.local"},
        )
        _ctx(conn, consultant)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'Acme')"),
            {"i": client, "c": consultant},
        )
        _ctx(conn, consultant, client)
        conn.execute(
            text("INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"),
            {"i": project, "cl": client, "c": consultant},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Ciclo passivo')"
            ),
            {"i": process, "p": project, "cl": client, "c": consultant},
        )
    w = {
        "consultant": str(consultant),
        "client": str(client),
        "project": str(project),
        "process": str(process),
    }
    yield w
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("DELETE FROM graph_outbox_dead_letter WHERE client_id = :cl"), {"cl": client}
        )
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant})
    neo4j_store.purge_client(str(client))
    gateway._staleness_cache.clear()


def _write_every_shape(w) -> dict[str, str]:
    """Un esemplare di ogni cosa che il write path proietta: nodi di tutte le
    label, relazione semantica, e tutti gli archi strutturali - compreso il
    ripiego sul processo della riga quando `affected_process_ids` e' vuoto."""
    c, cl, pj, pr = w["consultant"], w["client"], w["project"], w["process"]
    canonical.write_process_node(c, cl, pr, "Ciclo passivo", project_id=pj)
    cfo = canonical.write_entity(
        c, cl, "role", "CFO", project_id=pj, process_id=pr,
        attributes={"role_type": "CFO", "seniority": "executive", "nota": "non whitelisted"},
        confidence=0.8,
    )
    fattura = canonical.write_entity(c, cl, "activity", "Registrazione fattura",
                                     project_id=pj, process_id=pr)
    canonical.write_relation(c, cl, cfo, "approves", fattura, project_id=pj,
                             process_id=pr, confidence=0.7, confirmed=True)
    claim_a = canonical.write_claim(c, cl, "Il CFO approva sopra soglia.", "control",
                                    project_id=pj, process_id=pr, claim_status="confirmed")
    claim_b = canonical.write_claim(c, cl, "Nessuno approva, si paga e basta.", "control",
                                    project_id=pj, process_id=pr)
    canonical.write_gap(c, cl, "Soglia ignota", "Manca la cifra.", project_id=pj,
                        process_id=pr, severity="high")
    canonical.write_contradiction(c, cl, "Chi approva?", project_id=pj, process_id=pr,
                                  conflicting_claim_ids=[claim_a, claim_b])
    canonical.write_impact(c, cl, "Pagamenti non autorizzati", "compliance",
                           "Senza soglia si paga senza firma.", project_id=pj,
                           affected_process_ids=[pr], confidence=0.6)
    return {"cfo": cfo, "fattura": fattura}


def test_reprojection_matches_the_write_path(world):
    _write_every_shape(world)
    _drain_all()

    d = reproject.diff(world["consultant"], world["client"])

    assert d.clean, d.summary()
    assert d.expected_nodes == 8   # process + 2 entita' + 2 claim + gap + contraddizione + impatto
    # APPROVES + 2 HAS_CLAIM + BLOCKS (ripiego) + AFFECTS (ripiego) + 2 BETWEEN + AFFECTS impatto
    assert d.expected_edges == 8


def test_apply_rebuilds_a_lost_projection_and_is_idempotent(world):
    _write_every_shape(world)
    _drain_all()
    neo4j_store.purge_client(world["client"])

    lost = reproject.diff(world["consultant"], world["client"])
    assert len(lost.missing_nodes) == lost.expected_nodes
    assert len(lost.missing_edges) == lost.expected_edges

    first = reproject.apply(world["consultant"], world["client"])
    assert first.after.clean, first.after.summary()

    second = reproject.apply(world["consultant"], world["client"])
    assert second.before.clean
    assert second.deleted_nodes == 0 and second.deleted_edges == 0


def test_apply_removes_orphans_and_duplicates(world):
    ids = _write_every_shape(world)
    _drain_all()
    orphan = str(uuid.uuid4())
    with neo4j_store.get_driver().session() as neo:
        neo.run(
            "CREATE (:Entity {entity_id: $id, client_id: $cid, status: 'active'})",
            id=orphan, cid=world["client"],
        ).consume()
        neo.run(
            "MATCH (a:Entity {entity_id: $s}), (b:Entity {entity_id: $t}) "
            "CREATE (a)-[:APPROVES {client_id: $cid}]->(b)",
            s=ids["cfo"], t=ids["fattura"], cid=world["client"],
        ).consume()
        neo.run(
            "MATCH (n:Entity {entity_id: $id}) SET n.confidence = 0.01", id=ids["fattura"]
        ).consume()

    before = reproject.diff(world["consultant"], world["client"])
    assert ("Entity", orphan) in before.extra_nodes
    assert len(before.duplicate_edges) == 1
    assert before.drifted_nodes == [("Entity", ids["fattura"])]

    report = reproject.apply(world["consultant"], world["client"])
    assert report.after.clean, report.after.summary()


def test_graph_retrieve_says_when_the_projection_is_behind(world):
    """Un arco finito nel dead-letter non arriva mai in Neo4j. `graph_retrieve`
    deve dirlo; dopo la riparazione (`--apply --resolve-dead-letter`) non piu'."""
    ids = _write_every_shape(world)
    _drain_all()
    with neo4j_store.get_driver().session() as neo:
        neo.run(
            "MATCH (:Entity {entity_id: $s})-[r:APPROVES]->(:Entity {entity_id: $t}) DELETE r",
            s=ids["cfo"], t=ids["fattura"],
        ).consume()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO graph_outbox_dead_letter "
                "(id, aggregate_type, aggregate_id, consultant_id, client_id, op, payload, "
                " dedupe_key, created_at, attempts, last_error, reason) "
                "VALUES (:id, 'relation', :aid, :c, :cl, 'upsert', '{}'::jsonb, :dk, now(), "
                "        1, 'boom', 'payload non applicabile (test)')"
            ),
            {
                "id": random.randint(10**12, 10**13), "aid": ids["cfo"],
                "c": world["consultant"], "cl": world["client"], "dk": f"test:{uuid.uuid4()}",
            },
        )

    def _retrieve():
        gateway._staleness_cache.clear()
        return gateway.graph_retrieve(
            consultant_id=world["consultant"], client_id=world["client"],
            entity_names=["CFO"], scope_project_id=world["project"],
            scope_process_id=world["process"], max_hops=1,
        )

    stale = _retrieve()
    assert stale["staleness"]["dead_letter"] == 1, stale
    assert not any(m["relation"] == "APPROVES" for m in stale["matches"])

    report = reproject.apply(world["consultant"], world["client"])
    assert report.after.clean
    assert kg_reproject._resolve_dead_letter(world["client"]) == 1

    healed = _retrieve()
    assert "staleness" not in healed, healed
    assert any(m["relation"] == "APPROVES" for m in healed["matches"])


def test_uniqueness_constraints_exist_after_a_drain(world):
    _write_every_shape(world)
    _drain_all()
    with neo4j_store.get_driver().session() as neo:
        names = {r["name"] for r in neo.run("SHOW CONSTRAINTS YIELD name")}
    assert {"entity_entity_id_unique", "process_process_id_unique",
            "claim_claim_id_unique"} <= names
