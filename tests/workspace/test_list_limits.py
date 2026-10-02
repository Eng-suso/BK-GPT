"""Un elenco tagliato lo dice, invece di far credere di essere tutto.

B12. `list_clients` e `list_projects` non avevano nessun tetto: una sola
richiesta poteva tirare giu' l'intero workspace. Il tetto da solo pero' non
basta - taglierebbe in silenzio, e chi guarda crederebbe di vedere tutto -
quindi accanto c'e' il conteggio vero.
"""

import pytest
from fastapi.testclient import TestClient

from backend.settings import settings
from backend.workspace_database import (
    DEFAULT_LIST_LIMIT,
    count_clients,
    list_clients,
)


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@_needs_db
def test_a_list_never_returns_more_than_its_cap(client: TestClient):
    for index in range(6):
        client.post("/v1/workspace/clients", json={"name": f"Cliente tetto {index}"})

    assert len(list_clients(limit=3)) == 3
    # Un numero assurdo non diventa "nessun limite".
    assert len(list_clients(limit=10_000)) <= 2000


@_needs_db
def test_the_response_says_how_many_rows_exist(client: TestClient):
    for index in range(4):
        client.post("/v1/workspace/clients", json={"name": f"Cliente conteggio {index}"})

    response = client.get("/v1/workspace/clients?limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-DeliR-Returned"] == "2"
    # Il conteggio e' quello vero, non quello delle righe restituite: senza,
    # l'elenco tagliato sarebbe indistinguibile da un elenco completo.
    assert int(response.headers["X-DeliR-Total"]) >= 4
    assert response.headers["X-DeliR-Limit"] == "2"


@_needs_db
def test_without_a_limit_the_default_cap_applies(client: TestClient):
    response = client.get("/v1/workspace/clients")

    assert response.status_code == 200
    assert len(response.json()) <= DEFAULT_LIST_LIMIT
    assert int(response.headers["X-DeliR-Total"]) == count_clients()


@_needs_db
def test_projects_are_capped_and_counted_too(client: TestClient):
    created = client.post("/v1/workspace/clients", json={"name": "Cliente incarichi"})
    for index in range(3):
        client.post(
            "/v1/workspace/projects",
            json={"client_id": created.json()["id"], "name": f"Incarico {index}"},
        )

    response = client.get("/v1/workspace/projects?limit=1")

    assert len(response.json()) == 1
    assert int(response.headers["X-DeliR-Total"]) >= 3
