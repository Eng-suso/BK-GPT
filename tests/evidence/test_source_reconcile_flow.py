"""P1.13 — due file dello stesso processo che dicono cose diverse.

Il percorso e' quello vero: caricamento, conferma, lettura, estrazione, confronto
(modelli finti), coda del grafo, canonical, outbox, projector, Neo4j. Il
conflitto deve restare visibile con le due evidenze, nel workspace e nel grafo,
e sparire quando uno dei due file viene riestratto.

Servono le DSN workspace + canonical + NEO4J_PASSWORD.
"""

from __future__ import annotations

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
from backend.memory.knowledge_graph import neo4j_store, reproject  # noqa: E402
from backend.workspace_services.evidence import claims as claims_module  # noqa: E402
from backend.workspace_services.evidence import reconcile as reconcile_module  # noqa: E402
from backend.workspace_services.evidence.claims import ClaimExtraction  # noqa: E402
from backend.workspace_services.evidence.reconcile import Reconciliation  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

INTERVISTA = "Sopra i 50.000 EUR gli ordini li approva il CFO."
PROCEDURA = "Il CFO approva gli ordini sopra i 30.000 EUR."
SAP = "Le fatture si registrano in SAP."


@pytest.fixture()
def tenant() -> str:
    return f"riconc-{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def http(tenant: str):
    with TestClient(app, headers={"X-DeliR-Tenant-ID": tenant}) as client:
        yield client


@pytest.fixture()
def models(monkeypatch):
    """Estrazione: ogni frase del file e' un'affermazione. Confronto: le soglie
    divergono, SAP si conferma. `calls` conta i confronti pagati."""
    calls: list[str] = []

    def extract(**kwargs):
        user = kwargs["messages"][1].content
        claims = [
            {"statement": sentence, "segment": ordinal, "quote": sentence}
            for ordinal, sentence in ((1, INTERVISTA), (1, PROCEDURA), (2, SAP))
            if sentence in user
        ]
        return ClaimExtraction.model_validate({"claims": claims})

    def compare(**kwargs):
        user = kwargs["messages"][1].content
        calls.append(user)
        lines = user.splitlines()
        new = {line.split("] ", 1)[1]: int(line[2:].split("]")[0]) for line in lines if line.startswith("[N")}
        old = {
            line.split(") ", 1)[1]: int(line[2:].split("]")[0]) for line in lines if line.startswith("[E")
        }
        pairs = []
        thresholds = [s for s in (INTERVISTA, PROCEDURA) if s in new], [s for s in (INTERVISTA, PROCEDURA) if s in old]
        if thresholds[0] and thresholds[1]:
            pairs.append({
                "new": new[thresholds[0][0]], "existing": old[thresholds[1][0]], "relation": "diverge",
                "divergence_type": "incompatible", "explanation": "Soglie di approvazione diverse.",
            })
        if SAP in new and SAP in old:
            pairs.append({"new": new[SAP], "existing": old[SAP], "relation": "same", "explanation": "Stesso sistema."})
        return Reconciliation.model_validate({"pairs": pairs})

    monkeypatch.setattr(claims_module, "llm_run", extract)
    monkeypatch.setattr(reconcile_module, "llm_run", compare)
    return calls


@pytest.fixture()
def workspace(http: TestClient, tenant: str):
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    client = http.post("/v1/workspace/clients", json={"name": f"Riconc {uuid.uuid4().hex[:8]}"}).json()
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


def _confirm(http: TestClient, tenant: str, workspace: dict, name: str, body: str) -> dict:
    project, process = workspace["project"], workspace["process"]
    created = http.post(
        f"/v1/workspace/projects/{project['id']}/sources/upload",
        data={
            "roles": '["process_evidence"]',
            "retention": "persistent",
            "scopes": f'[{{"type":"process","id":"{process["id"]}"}}]',
        },
        files={"file": (f"{name}-{uuid.uuid4().hex[:6]}.md", body.encode(), "application/octet-stream")},
    ).json()
    assert http.post(f"/v1/workspace/sources/{created['id']}/verify").status_code == 200
    from backend.workers import source_worker

    while source_worker.drain_once(10, only_tenant_id=tenant):
        pass
    return created


def _source(http: TestClient, workspace: dict, source_id: str) -> dict:
    listed = http.get(f"/v1/workspace/projects/{workspace['project']['id']}/sources").json()
    return {item["id"]: item for item in listed}[source_id]


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


def _between(client_id: str) -> list[dict]:
    with neo4j_store.get_driver().session() as neo:
        return [
            record.data()
            for record in neo.run(
                "MATCH (x:Contradiction {client_id: $cid})-[:BETWEEN]->(c:Claim) "
                "RETURN x.contradiction_id AS contradiction, x.divergence_type AS type, "
                "       collect(c.claim_id) AS claims",
                cid=client_id,
            )
        ]


def _project_graph(landed, *, tries: int = 40, delay: float = 0.25) -> bool:
    from backend.workers.graph_worker import drain_once as drain_graph

    for _ in range(tries):
        drain_graph(limit=500)
        if landed():
            return True
        time.sleep(delay)
    return False


def _two_files(http, tenant, workspace):
    intervista = _confirm(http, tenant, workspace, "intervista", f"# Intervista\n\n{INTERVISTA}\n\n{SAP}")
    procedura = _confirm(http, tenant, workspace, "procedura", f"# Procedura\n\n{PROCEDURA}\n\n{SAP}")
    return intervista, procedura


def test_two_files_that_disagree_show_the_conflict_with_both_evidences(
    http: TestClient, tenant: str, models, workspace
):
    intervista, procedura = _two_files(http, tenant, workspace)

    # Il primo file non ha niente con cui confrontarsi: nessuna spesa.
    assert len(models) == 1
    assert _source(http, workspace, procedura["id"])["reconcile_status"] == "done"

    relations = http.get(f"/v1/workspace/sources/{procedura['id']}/relations").json()
    kinds = {relation["kind"]: relation for relation in relations}
    divergence = kinds["divergence"]
    assert divergence["divergence_type"] == "incompatible"
    assert divergence["claim"]["statement"] == PROCEDURA
    assert divergence["claim"]["anchor_ref"] == "§2"
    assert divergence["claim"]["quote"] == PROCEDURA and divergence["claim"]["quote_verified"] is True
    assert divergence["other"]["source_id"] == intervista["id"]
    assert divergence["other"]["statement"] == INTERVISTA
    assert divergence["other"]["anchor_ref"] == "§2"
    assert kinds["corroboration"]["other"]["statement"] == SAP

    # Lo stesso conflitto si vede anche dall'altro file, con i lati girati.
    [seen_from_other] = [
        r for r in http.get(f"/v1/workspace/sources/{intervista['id']}/relations").json() if r["kind"] == "divergence"
    ]
    assert seen_from_other["claim"]["statement"] == INTERVISTA
    assert seen_from_other["other"]["statement"] == PROCEDURA

    # Nel grafo: una contraddizione fra i due Claim, con le due frasi in Postgres.
    ids = _scope(tenant, workspace)
    [contradiction] = _rows(
        "SELECT id, divergence_type, conflicting_statements, conflicting_claim_ids FROM kg_contradiction",
        ids.client_id,
    )
    assert contradiction.divergence_type == "incompatible"
    assert set(contradiction.conflicting_statements) == {PROCEDURA, INTERVISTA}
    assert _project_graph(lambda: len(_between(ids.client_id)) == 1)
    [edge] = _between(ids.client_id)
    assert sorted(edge["claims"]) == sorted(str(c) for c in contradiction.conflicting_claim_ids)
    drift = reproject.diff(ids.consultant_id, ids.client_id)
    assert drift.clean, drift.summary()

    # Un'altra tenant non vede niente.
    with TestClient(app, headers={"X-DeliR-Tenant-ID": f"riconc-{uuid.uuid4().hex[:10]}"}) as stranger:
        assert stranger.get(f"/v1/workspace/sources/{procedura['id']}/relations").status_code == 404


def test_extracting_one_file_again_takes_its_old_conflicts_out(http: TestClient, tenant: str, models, workspace):
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    intervista, procedura = _two_files(http, tenant, workspace)
    ids = _scope(tenant, workspace)
    assert _project_graph(lambda: len(_between(ids.client_id)) == 1)

    # La procedura si riestrae: le sue affermazioni sono nuove, le relazioni
    # vecchie cadono con loro, e il confronto le ritrova.
    token = set_current_tenant_id(tenant)
    try:
        with wd.workspace_connection() as session:
            source = wd.tenant_row(session, wd.WorkspaceSource, procedura["id"])
            source.claims_status = "pending"
            source.claims_attempts = 0
            source.claims_next_attempt_at = wd.now_iso()
    finally:
        reset_current_tenant_id(token)
    from backend.workers import source_worker

    while source_worker.drain_once(10, only_tenant_id=tenant):
        pass

    contradictions = _rows("SELECT id FROM kg_contradiction", ids.client_id)
    assert len(contradictions) == 1
    assert _project_graph(
        lambda: [e["contradiction"] for e in _between(ids.client_id)] == [str(contradictions[0].id)]
    )
    relations = http.get(f"/v1/workspace/sources/{intervista['id']}/relations").json()
    assert sorted(r["kind"] for r in relations) == ["corroboration", "divergence"]
    drift = reproject.diff(ids.consultant_id, ids.client_id)
    assert drift.clean, drift.summary()
