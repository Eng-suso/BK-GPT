"""Fixture delle API di simulazione: client, processo con BPMN, motore finto."""

from collections.abc import Callable

import pytest


@pytest.fixture()
def api_client():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def new_bpmn_model(api_client) -> Callable[..., str]:
    """Crea cliente, progetto e processo; restituisce l'id del modello BPMN."""

    def create(headers: dict[str, str] | None = None) -> str:
        client_id = api_client.post("/v1/workspace/clients", json={"name": "Sim Client"}, headers=headers).json()["id"]
        project_id = api_client.post(
            "/v1/workspace/projects", json={"client_id": client_id, "name": "Sim Project"}, headers=headers
        ).json()["id"]
        process = api_client.post(
            f"/v1/workspace/projects/{project_id}/processes", json={"name": "Sim Process"}, headers=headers
        )
        assert process.status_code == 200, process.text
        return process.json()["bpmn_model_id"]

    return create


@pytest.fixture()
def fake_engine(monkeypatch) -> list:
    """Il motore non parte: ogni richiesta finisce nella lista e torna un risultato vuoto."""
    from backend.simulation.models import ProsimosSimulationResult

    sent: list = []

    async def engine(request):
        sent.append(request)
        return ProsimosSimulationResult(payload={"statsFile": "s.csv", "logFile": "e.csv"})

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", engine)
    return sent
