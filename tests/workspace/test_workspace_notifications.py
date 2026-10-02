"""La campanella dice cosa e' successo mentre il consulente guardava altrove.

Le date dei fatti di prova stanno nel futuro di proposito: il feed e' ordinato
dal piu' recente e tagliato, e su un workspace con dentro lavoro vero un fatto
datato oggi finirebbe sotto la soglia senza che il codice abbia niente che non
va.

Mostrava un `3` scritto a mano. Il lavoro pero' succede davvero in differita -
un piano si ricostruisce in coda, un confronto con le fonti gira dopo che il
disegno e' uscito, una simulazione finisce minuti dopo - e senza un posto dove
leggerlo ci si accorge di un rilievo solo riaprendo il processo per caso.

Gli avvisi si derivano dai fatti gia' agli atti: questi test fissano quali fatti
diventano un avviso, quali no, e che "letto" sia uno stato vero e non un badge
che si spegne da solo.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

NOTIFICATIONS = "/v1/workspace/notifications"


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def process(client):
    """Un processo vero sotto un cliente e un progetto, rimossi a fine test."""
    from backend import workspace_database

    marker = uuid.uuid4().hex[:8]
    created_client = client.post(
        "/v1/workspace/clients", json={"name": f"Avvisi {marker}"}
    ).json()
    project = client.post(
        "/v1/workspace/projects",
        json={"client_id": created_client["id"], "name": f"Progetto {marker}"},
    ).json()
    created = client.post(
        f"/v1/workspace/projects/{project['id']}/processes",
        json={"name": f"Ciclo passivo {marker}"},
    ).json()

    yield {"marker": marker, "client": created_client, "project": project, "process": created}

    workspace_database.delete_client(created_client["id"])


def _conformance_report(verdict: str, findings: int, audited_at: str) -> dict:
    return {
        "verdict": verdict,
        "process_id": "p",
        "findings": [{"id": f"f{index}"} for index in range(findings)],
        "audited_at": audited_at,
    }


def _record_conformance(bpmn_model_id: str, process_id: str, report: dict) -> None:
    """Registra un confronto sulla review del processo.

    La review nasce qui a mano: un processo appena creato non ne ha una, e
    prepararla davvero vorrebbe dire far girare il modello. Cio' che il test
    verifica e' cosa diventa un avviso, non come nasce un piano.
    """
    from backend import workspace_database, workspace_storage

    with workspace_storage.workspace_connection() as session:
        if session.get(workspace_storage.WorkspaceBpmnReview, bpmn_model_id) is None:
            session.add(
                workspace_storage.WorkspaceBpmnReview(
                    bpmn_model_id=bpmn_model_id,
                    tenant_id="local",
                    process_id=process_id,
                    version=1,
                    source_text="note del processo",
                    bpmn_brief="",
                    readiness_score=50,
                    missing_information_json="[]",
                    created_at="2030-09-20T08:00:00+00:00",
                    updated_at="2030-09-20T08:00:00+00:00",
                )
            )

    workspace_database.record_conformance_report(bpmn_model_id, report)


def _mine(response, marker: str) -> list[dict]:
    assert response.status_code == 200
    body = response.json()
    return [item for item in body["items"] if marker in item["process_name"]]


@_needs_db
def test_a_comparison_with_findings_becomes_a_notification(client, process):
    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("not_conformant", 2, "2030-09-20T09:00:00+00:00"),
    )

    items = _mine(client.get(NOTIFICATIONS), process["marker"])

    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "conformance_findings"
    assert item["count"] == 2
    assert item["project_name"] == process["project"]["name"]
    assert item["client_name"] == process["client"]["name"]
    assert item["read"] is False


@_needs_db
def test_a_clean_comparison_is_not_a_notification(client, process):
    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("conformant", 0, "2030-09-20T09:00:00+00:00"),
    )

    # Non c'e' niente da fare: un elenco di buone notizie insegna a non aprirlo.
    assert _mine(client.get(NOTIFICATIONS), process["marker"]) == []


@_needs_db
def test_reading_a_notification_sticks(client, process):
    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("not_conformant", 1, "2030-09-20T09:00:00+00:00"),
    )
    item = _mine(client.get(NOTIFICATIONS), process["marker"])[0]

    marked = client.post(f"{NOTIFICATIONS}/read", json={"ids": [item["id"]]})

    assert marked.status_code == 200
    again = _mine(client.get(NOTIFICATIONS), process["marker"])[0]
    assert again["read"] is True


@_needs_db
def test_a_new_state_comes_back_unread(client, process):
    model_id = process["process"]["bpmn_model_id"]
    _record_conformance(model_id, process["process"]["id"], _conformance_report("not_conformant", 1, "2030-09-20T09:00:00+00:00"))
    first = _mine(client.get(NOTIFICATIONS), process["marker"])[0]
    client.post(f"{NOTIFICATIONS}/read", json={"ids": [first["id"]]})

    # Un confronto nuovo e' un fatto nuovo, non lo stesso avviso gia' letto:
    # l'id porta con se' quando e' stato fatto.
    _record_conformance(model_id, process["process"]["id"], _conformance_report("not_conformant", 3, "2030-09-20T11:00:00+00:00"))
    latest = _mine(client.get(NOTIFICATIONS), process["marker"])[0]

    assert latest["id"] != first["id"]
    assert latest["read"] is False
    assert latest["count"] == 3


@_needs_db
def test_mark_all_read_clears_the_count(client, process):
    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("incomplete", 1, "2030-09-20T09:00:00+00:00"),
    )
    assert client.get(NOTIFICATIONS).json()["unread"] >= 1

    cleared = client.post(f"{NOTIFICATIONS}/read", json={})

    assert cleared.status_code == 200
    assert cleared.json()["unread"] == 0
    assert client.get(NOTIFICATIONS).json()["unread"] == 0


@_needs_db
def test_a_finished_simulation_is_a_notification(client, process):
    from backend import workspace_storage

    marker = process["marker"]
    with workspace_storage.workspace_connection() as session:
        session.add(
            workspace_storage.WorkspaceSimulationRun(
                tenant_id="local",
                bpmn_model_id=process["process"]["bpmn_model_id"],
                process_id=process["process"]["id"],
                scenario_name=f"Scenario {marker}",
                engine="prosimos",
                status="completed",
                request_json="{}",
                scenario_json="{}",
                result_json=json.dumps({"ok": True}),
                outputs_json="[]",
                created_at="2030-09-20T08:00:00+00:00",
                completed_at="2030-09-20T08:05:00+00:00",
            )
        )

    items = _mine(client.get(NOTIFICATIONS), marker)

    assert [item["kind"] for item in items] == ["simulation_done"]
    assert items[0]["detail"] == f"Scenario {marker}"


@_needs_db
def test_archived_work_stops_notifying(client, process):
    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("not_conformant", 2, "2030-09-20T09:00:00+00:00"),
    )
    assert _mine(client.get(NOTIFICATIONS), process["marker"])

    archived = client.post(
        f"/v1/workspace/projects/{process['project']['id']}/archive",
        json={"reason": "incarico chiuso"},
    )
    assert archived.status_code == 200

    # Un avviso su un incarico chiuso fa riaprire la cosa sbagliata.
    assert _mine(client.get(NOTIFICATIONS), process["marker"]) == []


@_needs_db
def test_notifications_do_not_cross_tenants(client, process, monkeypatch):
    from backend.security import set_current_tenant_id

    _record_conformance(
        process["process"]["bpmn_model_id"],
        process["process"]["id"],
        _conformance_report("not_conformant", 1, "2030-09-20T09:00:00+00:00"),
    )

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")

    try:
        response = client.get(
            NOTIFICATIONS,
            headers={
                "Authorization": "Bearer test-api-token",
                "X-DeliR-Tenant-ID": "tenant-estraneo",
            },
        )
    finally:
        set_current_tenant_id("local")

    assert response.status_code == 200
    assert _mine(response, process["marker"]) == []
