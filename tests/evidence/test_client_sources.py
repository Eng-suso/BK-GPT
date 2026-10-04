"""P1.16 — un file caricato per tutto il cliente.

Appartiene al cliente, non a un progetto: compare nelle Fonti di ogni progetto
del cliente, entra nel grafo a livello cliente, entra nel confronto dei file di
progetto, sopravvive alla cancellazione di un progetto e se ne va con il
cliente. I modelli sono finti.

Servono le DSN workspace + canonical + NEO4J_PASSWORD.
"""

from __future__ import annotations

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
from backend.memory.knowledge_graph import neo4j_store  # noqa: E402
from backend.workspace_services.evidence import claims as claims_module  # noqa: E402
from backend.workspace_services.evidence import reconcile as reconcile_module  # noqa: E402
from backend.workspace_services.evidence.claims import ClaimExtraction  # noqa: E402
from backend.workspace_services.evidence.reconcile import Reconciliation  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

POLICY = "Ogni ordine sopra i 10.000 EUR richiede tre preventivi."
PRASSI = "Gli ordini fino a 20.000 EUR si fanno con un solo preventivo."


@pytest.fixture()
def tenant() -> str:
    return f"cliente-{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def http(tenant: str):
    with TestClient(app, headers={"X-DeliR-Tenant-ID": tenant}) as client:
        yield client


@pytest.fixture()
def models(monkeypatch):
    def extract(**kwargs):
        user = kwargs["messages"][1].content
        claims = [
            {"statement": sentence, "segment": 1, "quote": sentence}
            for sentence in (POLICY, PRASSI)
            if sentence in user
        ]
        return ClaimExtraction.model_validate({"claims": claims})

    def compare(**kwargs):
        user = kwargs["messages"][1].content
        pairs = []
        if f"[N1] {PRASSI}" in user and POLICY in user:
            pairs.append({
                "new": 1, "existing": 1, "relation": "diverge",
                "divergence_type": "incompatible", "explanation": "Soglie dei preventivi diverse.",
            })
        return Reconciliation.model_validate({"pairs": pairs})

    monkeypatch.setattr(claims_module, "llm_run", extract)
    monkeypatch.setattr(reconcile_module, "llm_run", compare)


@pytest.fixture()
def workspace(http: TestClient, tenant: str):
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    client = http.post("/v1/workspace/clients", json={"name": f"Cliente {uuid.uuid4().hex[:8]}"}).json()
    acquisti = http.post("/v1/workspace/projects", json={"client_id": client["id"], "name": "Acquisti"}).json()
    tesoreria = http.post("/v1/workspace/projects", json={"client_id": client["id"], "name": "Tesoreria"}).json()
    try:
        yield {"client": client, "acquisti": acquisti, "tesoreria": tesoreria}
    finally:
        token = set_current_tenant_id(tenant)
        try:
            canonical_client = canonical_scope.resolve_client_id(acquisti["id"])
        except Exception:  # noqa: BLE001 - il progetto puo' essere gia' stato cancellato
            canonical_client = None
        finally:
            reset_current_tenant_id(token)
        if canonical_client:
            with MIGRATOR.begin() as conn:
                conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": canonical_client})
            neo4j_store.purge_client(canonical_client)


def _upload_to_client(http: TestClient, client_id: str, body: str, name: str = "policy-acquisti.md"):
    return http.post(
        f"/v1/workspace/clients/{client_id}/sources/upload",
        data={"roles": '["policy"]', "retention": "persistent"},
        files={"file": (name, body.encode(), "application/octet-stream")},
    )


def _drain(tenant: str) -> None:
    from backend.workers import source_worker

    while source_worker.drain_once(10, only_tenant_id=tenant):
        pass


def _resolve(client_name: str) -> str:
    from backend.memory.scope import _slug

    with MIGRATOR.begin() as conn:
        # RLS anche per il migrator (FORCE): senza consulente non si vede niente.
        conn.execute(text("SELECT set_config('app.current_consultant_id', :c, true)"),
                     {"c": settings.default_consultant_id})
        return str(
            conn.execute(
                text("SELECT id FROM client WHERE workspace_id = :w"), {"w": f"client:{_slug(client_name)}"}
            ).scalar_one()
        )


def _rows(sql: str, client: str, **params) -> list:
    with MIGRATOR.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_consultant_id', :c, true)"),
                     {"c": settings.default_consultant_id})
        conn.execute(text("SELECT set_config('app.current_client_id', :c, true)"), {"c": client})
        return conn.execute(text(sql), params).all()


def test_a_client_file_shows_in_every_project_and_is_not_duplicated(http: TestClient, tenant: str, workspace):
    client, acquisti, tesoreria = workspace["client"], workspace["acquisti"], workspace["tesoreria"]
    first = _upload_to_client(http, client["id"], f"# Policy\n\n{POLICY}")
    assert first.status_code == 201, first.text
    source = first.json()
    assert source["project_id"] is None
    assert source["client_id"] == client["id"]

    again = _upload_to_client(http, client["id"], f"# Policy\n\n{POLICY}", name="copia.md")
    assert again.status_code == 200
    assert again.json()["id"] == source["id"]

    for project in (acquisti, tesoreria):
        listed = http.get(f"/v1/workspace/projects/{project['id']}/sources").json()
        assert [item["id"] for item in listed] == [source["id"]]
    assert [item["id"] for item in http.get(f"/v1/workspace/clients/{client['id']}/sources").json()] == [source["id"]]

    with TestClient(app, headers={"X-DeliR-Tenant-ID": f"cliente-{uuid.uuid4().hex[:10]}"}) as stranger:
        assert stranger.get(f"/v1/workspace/clients/{client['id']}/sources").status_code == 404
        assert _upload_to_client(stranger, client["id"], "altro").status_code == 400


def test_a_confirmed_client_file_reaches_the_graph_and_the_comparison_of_project_files(
    http: TestClient, tenant: str, models, workspace
):
    client, acquisti = workspace["client"], workspace["acquisti"]
    policy = _upload_to_client(http, client["id"], f"# Policy\n\n{POLICY}").json()
    assert http.post(f"/v1/workspace/sources/{policy['id']}/verify").status_code == 200
    _drain(tenant)

    listed = {s["id"]: s for s in http.get(f"/v1/workspace/clients/{client['id']}/sources").json()}
    assert listed[policy["id"]]["claims_status"] == "done"
    assert listed[policy["id"]]["reconcile_status"] == "done"
    # Confermare una fonte del cliente non rimette in coda i piani dei processi.
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(tenant)
    try:
        with wd.workspace_connection() as session:
            queued = session.execute(
                text("SELECT count(*) FROM workspace_plan_materializations WHERE tenant_id = :t"), {"t": tenant}
            ).scalar_one()
    finally:
        reset_current_tenant_id(token)
    assert queued == 0

    canonical_client = _resolve(client["name"])
    [kg_source] = _rows(
        "SELECT id, project_id FROM kg_source WHERE workspace_source_id = :ws", canonical_client, ws=policy["id"]
    )
    assert kg_source.project_id is None
    assert len(_rows("SELECT id FROM kg_claim WHERE source_ids @> ARRAY[CAST(:s AS uuid)]",
                     canonical_client, s=str(kg_source.id))) == 1

    # Un file di progetto si confronta anche con la fonte del cliente.
    process = http.post(f"/v1/workspace/projects/{acquisti['id']}/processes", json={"name": "P2P"}).json()
    prassi = http.post(
        f"/v1/workspace/projects/{acquisti['id']}/sources/upload",
        data={
            "roles": '["process_evidence"]', "retention": "persistent",
            "scopes": f'[{{"type":"process","id":"{process["id"]}"}}]',
        },
        files={"file": ("intervista.md", f"# Intervista\n\n{PRASSI}".encode(), "application/octet-stream")},
    ).json()
    assert http.post(f"/v1/workspace/sources/{prassi['id']}/verify").status_code == 200
    _drain(tenant)

    [divergence] = http.get(f"/v1/workspace/sources/{prassi['id']}/relations").json()
    assert divergence["other"]["source_id"] == policy["id"]
    assert divergence["other"]["statement"] == POLICY
    seen_from_client = http.get(f"/v1/workspace/sources/{policy['id']}/relations").json()
    assert [r["other"]["source_id"] for r in seen_from_client] == [prassi["id"]]
    assert len(_rows("SELECT id FROM kg_contradiction", canonical_client)) == 1


def test_a_client_file_outlives_a_project_and_leaves_with_the_client(
    http: TestClient, tenant: str, models, workspace
):
    client, acquisti, tesoreria = workspace["client"], workspace["acquisti"], workspace["tesoreria"]
    policy = _upload_to_client(http, client["id"], f"# Policy\n\n{POLICY}").json()
    http.post(f"/v1/workspace/sources/{policy['id']}/verify")
    _drain(tenant)
    canonical_client = _resolve(client["name"])

    assert http.delete(f"/v1/workspace/projects/{acquisti['id']}").status_code in (200, 204)
    listed = http.get(f"/v1/workspace/projects/{tesoreria['id']}/sources").json()
    assert [item["id"] for item in listed] == [policy["id"]]
    assert _rows("SELECT id FROM kg_source WHERE workspace_source_id = :ws", canonical_client, ws=policy["id"])

    assert http.delete(f"/v1/workspace/clients/{client['id']}").status_code in (200, 204)
    assert not _rows("SELECT id FROM kg_source WHERE workspace_source_id = :ws", canonical_client, ws=policy["id"])
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(tenant)
    try:
        assert wd.get_project_source(policy["id"]) is None
    finally:
        reset_current_tenant_id(token)
