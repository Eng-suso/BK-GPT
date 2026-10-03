"""P1.14 — le affermazioni di un file caricato arrivano nel grafo.

Il percorso e' quello vero: caricamento, conferma, lettura, estrazione (modello
finto), coda del grafo, canonical, outbox, projector, Neo4j. Nel grafo deve
esserci il cammino Source -HAS_EVIDENCE-> Evidence -SUPPORTS-> Claim, e nessun
testo: le parole del file restano in Postgres (B+).

Servono le DSN workspace + canonical + NEO4J_PASSWORD.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.workspace_database_url,
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL + le DSN canonical + NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend.app import app  # noqa: E402
from backend.memory import scope as canonical_scope  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store, reproject  # noqa: E402
from backend.workspace_services.evidence import claims as claims_module  # noqa: E402
from backend.workspace_services.evidence.claims import ClaimExtraction  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

SOGLIA = "Il CFO approva gli ordini sopra i 30.000 EUR."
PROCEDURA = f"# Procedura acquisti\n\n{SOGLIA}\n\nSotto soglia approva il buyer.".encode()
STATEMENT = "Gli ordini sopra i 30.000 EUR li approva il CFO."


@pytest.fixture()
def tenant() -> str:
    return f"grafo-{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def http(tenant: str):
    with TestClient(app, headers={"X-DeliR-Tenant-ID": tenant}) as client:
        yield client


@pytest.fixture()
def model(monkeypatch):
    def run(**_kwargs):
        return ClaimExtraction.model_validate(
            {"claims": [{"statement": STATEMENT, "segment": 1, "quote": SOGLIA}]}
        )

    monkeypatch.setattr(claims_module, "llm_run", run)


@pytest.fixture()
def workspace(http: TestClient, tenant: str):
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    client = http.post("/v1/workspace/clients", json={"name": f"Grafo {uuid.uuid4().hex[:8]}"}).json()
    project = http.post("/v1/workspace/projects", json={"client_id": client["id"], "name": "Acquisti"}).json()
    process = http.post(
        f"/v1/workspace/projects/{project['id']}/processes", json={"name": f"P2P {uuid.uuid4().hex[:6]}"}
    ).json()
    try:
        yield {"project": project, "process": process}
    finally:
        token = set_current_tenant_id(tenant)
        try:
            canonical_client = canonical_scope.resolve_client_id(project["id"])
        finally:
            reset_current_tenant_id(token)
        if canonical_client:
            with MIGRATOR.begin() as conn:
                conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": canonical_client})
            neo4j_store.purge_client(canonical_client)


def _confirmed_source(http: TestClient, tenant: str, workspace: dict) -> dict:
    project, process = workspace["project"], workspace["process"]
    created = http.post(
        f"/v1/workspace/projects/{project['id']}/sources/upload",
        data={
            "roles": '["process_evidence"]',
            "retention": "persistent",
            "scopes": f'[{{"type":"process","id":"{process["id"]}"}}]',
        },
        files={"file": (f"procedura-{uuid.uuid4().hex[:6]}.md", PROCEDURA, "application/octet-stream")},
    ).json()
    assert http.post(f"/v1/workspace/sources/{created['id']}/verify").status_code == 200
    _drain_sources(tenant)
    return created


def _drain_sources(tenant: str) -> None:
    from backend.workers import source_worker

    while source_worker.drain_once(10, only_tenant_id=tenant):
        pass


def _scope(tenant: str, workspace: dict) -> canonical_scope.ScopeIds:
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(tenant)
    try:
        return canonical_scope.resolve(workspace["project"]["id"], workspace["process"]["id"])
    finally:
        reset_current_tenant_id(token)


def _rows(sql: str, client: str, **params) -> list:
    with MIGRATOR.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_consultant_id', :c, true)"),
                     {"c": settings.default_consultant_id})
        conn.execute(text("SELECT set_config('app.current_client_id', :c, true)"), {"c": client})
        return conn.execute(text(sql), params).all()


def _project_graph(landed, *, tries: int = 40, delay: float = 0.25) -> bool:
    from backend.workers.graph_worker import drain_once as drain_graph

    for _ in range(tries):
        drain_graph(limit=500)
        if landed():
            return True
        time.sleep(delay)
    return False


def _paths(client_id: str) -> list[dict]:
    with neo4j_store.get_driver().session() as neo:
        return [
            record.data()
            for record in neo.run(
                "MATCH (s:Source {client_id: $cid})-[:HAS_EVIDENCE]->(e:Evidence)"
                "-[:SUPPORTS]->(c:Claim) "
                "RETURN s.source_id AS source, e.anchor AS anchor, c.claim_id AS claim, "
                "       properties(s) AS sp, properties(e) AS ep, properties(c) AS cp",
                cid=client_id,
            )
        ]


def test_confirmed_file_reaches_the_graph_as_source_evidence_claim(
    http: TestClient, tenant: str, model, workspace
):
    created = _confirmed_source(http, tenant, workspace)
    sources = {s["id"]: s for s in http.get(f"/v1/workspace/projects/{workspace['project']['id']}/sources").json()}
    assert sources[created["id"]]["claims_status"] == "done"

    ids = _scope(tenant, workspace)
    [source] = _rows(
        "SELECT id, process_id, title FROM kg_source WHERE workspace_source_id = :ws",
        ids.client_id, ws=created["id"],
    )
    assert str(source.process_id) == ids.process_id
    [claim] = _rows(
        "SELECT c.statement, c.quote, c.quote_verified, e.anchor, c.source_ids "
        "FROM kg_claim c JOIN kg_evidence e ON e.id = c.evidence_id "
        "WHERE e.source_id = :sid",
        ids.client_id, sid=source.id,
    )
    assert claim.statement == STATEMENT
    assert claim.quote == SOGLIA and claim.quote_verified is True
    assert claim.anchor == "§2"
    assert [str(s) for s in claim.source_ids] == [str(source.id)]

    assert _project_graph(lambda: len(_paths(ids.client_id)) == 1)
    [path] = _paths(ids.client_id)
    assert path["source"] == str(source.id) and path["anchor"] == "§2"
    # B+: nessuna parola del file arriva in Neo4j
    projected = json.dumps([path["sp"], path["ep"], path["cp"]])
    for words in (SOGLIA, STATEMENT, source.title, "30.000"):
        assert words not in projected
    # cio' che il write path ha proiettato e' cio' che Postgres dice di avere
    drift = reproject.diff(ids.consultant_id, ids.client_id)
    assert drift.clean, drift.summary()


def test_extracting_again_replaces_instead_of_duplicating(
    http: TestClient, tenant: str, model, workspace
):
    created = _confirmed_source(http, tenant, workspace)
    ids = _scope(tenant, workspace)
    segment = canonical.SourceSegment(1, "§2", {"paragraph": 2})
    claim = canonical.SourceClaim(STATEMENT, 1, SOGLIA, True)
    for _ in range(2):
        counts = canonical.write_source_claims(
            consultant_id=ids.consultant_id, client_id=ids.client_id,
            project_id=ids.project_id, process_id=ids.process_id,
            workspace_source_id=created["id"], title="procedura.md", content_hash="h",
            segments=[segment], claims=[claim],
        )
        assert counts == {"source": 1, "evidence": 1, "claims": 1}

    for table in ("kg_evidence", "kg_claim"):
        [row] = _rows(
            f"SELECT count(*) AS n FROM {table} WHERE project_id = CAST(:pj AS uuid)",
            ids.client_id, pj=ids.project_id,
        )
        assert row.n == 1, table
    assert _project_graph(lambda: len(_paths(ids.client_id)) == 1)


def test_a_claim_on_a_segment_that_does_not_exist_stays_out(tenant: str, http, model, workspace):
    created = _confirmed_source(http, tenant, workspace)
    ids = _scope(tenant, workspace)
    counts = canonical.write_source_claims(
        consultant_id=ids.consultant_id, client_id=ids.client_id,
        project_id=ids.project_id, process_id=ids.process_id,
        workspace_source_id=created["id"], title="procedura.md", content_hash="h",
        segments=[canonical.SourceSegment(1, "§2", {})],
        claims=[canonical.SourceClaim(STATEMENT, 7, SOGLIA, True)],
    )
    assert counts == {"source": 1, "evidence": 0, "claims": 0}


def test_deleting_the_process_takes_the_file_out_of_the_graph(
    http: TestClient, tenant: str, model, workspace
):
    _confirmed_source(http, tenant, workspace)
    ids = _scope(tenant, workspace)
    assert _project_graph(lambda: len(_paths(ids.client_id)) == 1)

    assert http.delete(f"/v1/workspace/processes/{workspace['process']['id']}").status_code in (200, 204)
    assert _project_graph(lambda: not _paths(ids.client_id))
    with neo4j_store.get_driver().session() as neo:
        left = neo.run(
            "MATCH (n {client_id: $cid}) WHERE n:Source OR n:Evidence RETURN count(n) AS c",
            cid=ids.client_id,
        ).single()["c"]
    assert left == 0
    for table in ("kg_source", "kg_evidence"):
        [row] = _rows(
            f"SELECT count(*) AS n FROM {table} WHERE project_id = CAST(:pj AS uuid)",
            ids.client_id, pj=ids.project_id,
        )
        assert row.n == 0, table
