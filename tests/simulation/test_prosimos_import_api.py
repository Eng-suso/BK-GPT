"""B1b: lo scenario Prosimos o SIMOD passa dal server e si simula cosi' com'e'.

Serve il database (come gli altri test dell'API): gira con la suite completa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "datasets" / "extraneous-delays" / "inputs"


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def _bpmn_model_id(client) -> str:
    client_id = client.post(
        "/v1/workspace/clients", json={"name": "B1b Client"}
    ).json()["id"]
    project_id = client.post(
        "/v1/workspace/projects", json={"client_id": client_id, "name": "B1b Project"}
    ).json()["id"]
    process = client.post(
        f"/v1/workspace/projects/{project_id}/processes", json={"name": "B1b Process"}
    )
    assert process.status_code == 200
    return process.json()["bpmn_model_id"]


def _scenario(name: str) -> tuple[dict, str]:
    path = INPUTS / name
    return json.loads(
        path.with_suffix(".json").read_text(encoding="utf-8")
    ), path.with_suffix(".bpmn").read_text(encoding="utf-8")


def test_a_simod_scenario_comes_back_as_a_model_with_notes(client):
    bpmn_model_id = _bpmn_model_id(client)
    scenario, bpmn = _scenario("real-life/BPIC_2012_W")

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bpmn_model_id"] == bpmn_model_id
    assert len(body["model"]["activities"]) == len(
        scenario["task_resource_distribution"]
    )
    assert body["simod"]["model_type"] == scenario["model_type"]
    assert all(
        note["kind"] in {"info", "approximated"} and note["message"]
        for note in body["notes"]
    )


def test_a_scenario_that_would_lose_something_is_a_400_with_the_reason(client):
    bpmn_model_id = _bpmn_model_id(client)
    scenario, bpmn = _scenario("synthetic/Insurance_Claims")
    scenario["batch_processing"] = [{"task_id": "x"}]

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )

    assert response.status_code == 400
    assert "batch" in response.json()["error"]["message"]


def test_an_unknown_process_is_a_404(client):
    response = client.post(
        "/v1/workspace/bpmn-models/nope/prosimos-import", json={"scenario": {}}
    )
    assert response.status_code == 404


def test_the_imported_model_runs_as_it_is(client, monkeypatch):
    from backend.simulation.models import ProsimosSimulationResult
    from tests.simulation.engine_log import ENGINE_LOG

    sent: list = []

    async def fake_engine(request):
        sent.append(request)
        return ProsimosSimulationResult(
            payload={"statsFile": "s.csv", "logFile": "e.csv"}, event_log_csv=ENGINE_LOG
        )

    monkeypatch.setattr(
        "backend.simulation.service.run_prosimos_simulation", fake_engine
    )
    bpmn_model_id = _bpmn_model_id(client)
    scenario, bpmn = _scenario("synthetic/Loan_Application_3_timers")
    imported = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    ).json()

    run = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs",
        json={
            "model": imported["model"],
            "current_bpmn_xml": bpmn,
            "total_cases": 50,
            "scenario_name": "Scenario importato",
        },
    )

    assert run.status_code == 200, run.text
    assert sent, "il run non e' arrivato al motore"
    engine_scenario = sent[0].scenario.model_dump(mode="json")
    received = {
        e["event_id"]: e for e in engine_scenario["payload"]["event_distribution"]
    }
    # Le attese dei tre timer arrivano al motore con la durata dello scenario.
    for event in scenario["event_distribution"]:
        got = received[event["event_id"]]
        assert got["distribution_name"] == event["distribution_name"]
        assert [float(p["value"]) for p in got["distribution_params"]] == [
            float(p["value"]) for p in event["distribution_params"]
        ]
