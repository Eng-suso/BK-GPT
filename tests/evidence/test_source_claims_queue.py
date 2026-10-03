"""P1.12 dal gesto del consulente alle affermazioni salvate.

L'estrazione parte solo da un gesto del consulente: la conferma del file, o il
suo invio in chat. Il modello e' finto: qui si prova il percorso, non la sua
intelligenza.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.settings import settings
from backend.workspace_services.evidence import claims as claims_module
from backend.workspace_services.evidence.claims import ClaimExtraction

pytestmark = pytest.mark.skipif(not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL")

PROCEDURA = b"# Procedura acquisti\n\nIl CFO approva gli ordini sopra i 30.000 EUR.\n\nSotto soglia approva il buyer."


@pytest.fixture()
def tenant() -> str:
    return f"claims-{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def http(tenant: str):
    with TestClient(app, headers={"X-DeliR-Tenant-ID": tenant}) as client:
        yield client


@pytest.fixture()
def model(monkeypatch):
    calls: list[dict] = []

    def run(**kwargs):
        calls.append(kwargs)
        return ClaimExtraction.model_validate(
            {
                "claims": [
                    {
                        "statement": "Gli ordini sopra i 30.000 EUR li approva il CFO.",
                        "segment": 1,
                        "quote": "Il CFO approva gli ordini sopra i 30.000 EUR.",
                    }
                ]
            }
        )

    monkeypatch.setattr(claims_module, "llm_run", run)
    return calls


def _project(http: TestClient) -> tuple[dict, dict]:
    client = http.post("/v1/workspace/clients", json={"name": f"Claims {uuid.uuid4().hex[:8]}"}).json()
    project = http.post("/v1/workspace/projects", json={"client_id": client["id"], "name": "Acquisti"}).json()
    process = http.post(f"/v1/workspace/projects/{project['id']}/processes", json={"name": "Procure to pay"}).json()
    return project, process


def _upload(http: TestClient, project: dict, process: dict, name: str, payload: bytes) -> dict:
    return http.post(
        f"/v1/workspace/projects/{project['id']}/sources/upload",
        data={
            "roles": '["process_evidence"]',
            "retention": "persistent",
            "scopes": f'[{{"type":"process","id":"{process["id"]}"}}]',
        },
        files={"file": (name, payload, "application/octet-stream")},
    ).json()


def _drain(tenant: str) -> None:
    from backend.workers import source_worker

    while source_worker.drain_once(10, only_tenant_id=tenant):
        pass


def _source(http: TestClient, project: dict, source_id: str) -> dict:
    return {item["id"]: item for item in http.get(f"/v1/workspace/projects/{project['id']}/sources").json()}[source_id]


def test_nothing_is_extracted_until_the_consultant_confirms(http: TestClient, tenant: str, model):
    project, process = _project(http)
    created = _upload(http, project, process, f"procedura-{uuid.uuid4().hex[:6]}.md", PROCEDURA)
    _drain(tenant)

    # Letto ma non confermato: nessuna spesa.
    assert model == []
    assert _source(http, project, created["id"])["claims_status"] is None

    assert http.post(f"/v1/workspace/sources/{created['id']}/verify").status_code == 200
    assert _source(http, project, created["id"])["claims_status"] == "pending"
    _drain(tenant)

    assert len(model) == 1
    assert _source(http, project, created["id"])["claims_status"] == "done"
    [claim] = http.get(f"/v1/workspace/sources/{created['id']}/claims").json()
    assert claim["statement"] == "Gli ordini sopra i 30.000 EUR li approva il CFO."
    assert claim["anchor_ref"] == "§2"
    assert claim["quote_verified"] is True


def test_confirming_again_does_not_pay_twice_and_another_tenant_sees_nothing(
    http: TestClient, tenant: str, model
):
    project, process = _project(http)
    created = _upload(http, project, process, f"procedura-{uuid.uuid4().hex[:6]}.md", PROCEDURA)
    http.post(f"/v1/workspace/sources/{created['id']}/verify")
    _drain(tenant)
    assert len(model) == 1

    # Una seconda conferma non rimette in coda un'estrazione gia' fatta.
    assert http.post(f"/v1/workspace/sources/{created['id']}/verify").status_code == 200
    assert _source(http, project, created["id"])["claims_status"] == "done"
    _drain(tenant)
    assert len(model) == 1

    with TestClient(app, headers={"X-DeliR-Tenant-ID": f"claims-{uuid.uuid4().hex[:10]}"}) as stranger:
        assert stranger.get(f"/v1/workspace/sources/{created['id']}/claims").status_code == 404


def test_sending_a_file_in_chat_confirms_it_even_while_it_is_being_read(
    http: TestClient, tenant: str, model, monkeypatch
):
    import io

    from docx import Document

    from backend.api.routes import chat as chat_routes
    from backend.workspace_services.evidence import documents

    project, process = _project(http)
    word = Document()
    word.add_paragraph("Procedura")
    stream = io.BytesIO()
    word.save(stream)
    created = _upload(http, project, process, f"procedura-{uuid.uuid4().hex[:6]}.docx", stream.getvalue())
    assert created["acquisition_status"] == "pending"

    monkeypatch.setattr(chat_routes, "stream_agent_text", lambda **_kwargs: "Ricevuto.")
    thread = http.post(
        "/v1/consultant-chat/sessions", json={"model_name": "gpt-test", "scope": {"type": "consultant"}}
    ).json()["thread_id"]
    sent = http.post(
        f"/v1/consultant-chat/sessions/{thread}/messages",
        json={
            "message": "Ecco la procedura",
            "attachments": [
                {"kind": "source", "id": created["id"], "label": created["name"], "project_id": project["id"]}
            ],
        },
    )
    assert sent.status_code == 200

    # Ancora in lettura: confermato dopo, non adesso.
    assert _source(http, project, created["id"])["status"] != "approved"

    from tests.evidence.test_document_evidence import _procedure

    monkeypatch.setattr(documents, "convert", lambda filename, payload, **_options: (_procedure(), []))
    _drain(tenant)

    source = _source(http, project, created["id"])
    assert source["status"] == "approved"
    assert source["claims_status"] == "done"
    assert len(model) == 1


def test_a_failed_extraction_is_retried_and_then_says_why(http: TestClient, tenant: str, monkeypatch):
    from backend import workspace_database as wd

    def broken(**_kwargs):
        raise RuntimeError("provider giu'")

    monkeypatch.setattr(claims_module, "llm_run", broken)
    project, process = _project(http)
    created = _upload(http, project, process, f"procedura-{uuid.uuid4().hex[:6]}.md", PROCEDURA)
    http.post(f"/v1/workspace/sources/{created['id']}/verify")

    from backend.workspace_storage import WorkspaceSource

    for _ in range(wd.CLAIMS_MAX_ATTEMPTS + 1):
        _drain(tenant)
        with wd.workspace_connection() as session:
            row = session.get(WorkspaceSource, created["id"])
            if row.claims_status == "pending":
                row.claims_next_attempt_at = "1970-01-01T00:00:00+00:00"

    source = _source(http, project, created["id"])
    assert source["claims_status"] == "failed"
    assert "RuntimeError" in source["claims_error"]
    assert http.get(f"/v1/workspace/sources/{created['id']}/claims").json() == []
