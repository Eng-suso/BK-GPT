"""La sezione Modelli mostra i disegni che esistono, non un "in arrivo".

Ogni processo ha il suo modello BPMN, ma l'unico modo di trovarlo era aprire
cliente, progetto e processo uno per uno. Questi test fissano cosa la libreria
deve dire di ogni modello per essere utile - se il disegno c'e', quante
versioni ha - e cosa non deve mostrare: il lavoro archiviato e quello di un
altro tenant.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings
from tests.test_simulation import MINIMAL_BPMN


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

MODELS = "/v1/workspace/models"


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def engagement(client):
    """Un cliente con un progetto e due processi, rimosso a fine test."""
    from backend import workspace_database

    marker = uuid.uuid4().hex[:8]
    created_client = client.post(
        "/v1/workspace/clients", json={"name": f"Libreria {marker}"}
    ).json()
    project = client.post(
        "/v1/workspace/projects",
        json={"client_id": created_client["id"], "name": f"Progetto {marker}"},
    ).json()
    drawn = client.post(
        f"/v1/workspace/projects/{project['id']}/processes",
        json={"name": f"Ciclo passivo {marker}"},
    ).json()
    empty = client.post(
        f"/v1/workspace/projects/{project['id']}/processes",
        json={"name": f"Accettazione merce {marker}"},
    ).json()

    yield {
        "client": created_client,
        "project": project,
        "drawn": drawn,
        "empty": empty,
    }

    workspace_database.delete_client(created_client["id"])


def _by_model(response) -> dict[str, dict]:
    assert response.status_code == 200
    return {item["bpmn_model_id"]: item for item in response.json()}


@_needs_db
def test_the_library_lists_every_process_model_with_where_it_lives(client, engagement):
    models = _by_model(client.get(MODELS))

    drawn = models[engagement["drawn"]["bpmn_model_id"]]
    assert drawn["process_id"] == engagement["drawn"]["id"]
    assert drawn["project_name"] == engagement["project"]["name"]
    assert drawn["client_name"] == engagement["client"]["name"]
    assert engagement["empty"]["bpmn_model_id"] in models


@_needs_db
def test_a_saved_diagram_is_told_apart_from_an_empty_model(client, engagement):
    saved = client.put(
        f"/v1/workspace/bpmn-models/{engagement['drawn']['bpmn_model_id']}",
        json={"xml": MINIMAL_BPMN},
    )
    assert saved.status_code == 200

    models = _by_model(client.get(MODELS))

    # Un processo appena creato ha il modello ma non il disegno: la libreria
    # deve dirlo, altrimenti si apre un canvas vuoto credendo di trovarci il
    # processo.
    assert models[engagement["drawn"]["bpmn_model_id"]]["has_diagram"] is True
    assert models[engagement["empty"]["bpmn_model_id"]]["has_diagram"] is False
    assert models[engagement["drawn"]["bpmn_model_id"]]["version_count"] >= 1


@_needs_db
def test_archived_work_stays_out_of_the_library(client, engagement):
    archived = client.post(
        f"/v1/workspace/projects/{engagement['project']['id']}/archive",
        json={"reason": "incarico chiuso"},
    )
    assert archived.status_code == 200

    models = _by_model(client.get(MODELS))

    assert engagement["drawn"]["bpmn_model_id"] not in models
    assert engagement["empty"]["bpmn_model_id"] not in models


@_needs_db
def test_another_tenant_does_not_see_these_models(client, engagement, monkeypatch):
    from backend.security import set_current_tenant_id

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "local")

    try:
        response = client.get(
            MODELS,
            headers={
                "Authorization": "Bearer test-api-token",
                "X-DeliR-Tenant-ID": "tenant-estraneo",
            },
        )
    finally:
        set_current_tenant_id("local")

    models = _by_model(response)
    assert engagement["drawn"]["bpmn_model_id"] not in models
