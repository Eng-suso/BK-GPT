"""B1b: lo scenario Prosimos o SIMOD passa dal server e si simula cosi' com'e'.

Serve il database (come gli altri test dell'API): gira con la suite completa.
"""

from __future__ import annotations

import json
import os
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
        note["kind"] in {"info", "approximated", "warning"} and note["message"]
        for note in body["notes"]
    )


def test_procure_to_pay_warns_about_denser_arrivals_and_keeps_them(client):
    """IMP-01: l'avviso arriva al consulente; gli arrivi restano quelli del file."""
    bpmn_model_id = _bpmn_model_id(client)
    scenario, bpmn = _scenario("synthetic/Procure_to_Pay_3_timers")

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    warnings = [n for n in body["notes"] if n["topic"] == "arrivals_faster"]
    assert [n["kind"] for n in warnings] == ["warning"]
    assert "circa il 45% di casi in più" in warnings[0]["message"]
    assert body["model"]["arrival"]["interarrival"] == {
        "kind": "exponential",
        "mean": 1805.0,
        "minimum": 5.0,
        "maximum": 3600.0,
    }


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


def test_a_fuzzy_scenario_reaches_the_engine_with_its_probabilities(client, monkeypatch):
    """CAL-01: la disponibilita' probabilistica di SIMOD arriva al motore intatta."""
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
    scenario, bpmn = _scenario("synthetic/Insurance_Claims")
    scenario["model_type"] = "FUZZY"
    scenario["granule_size"] = {"value": 60, "time_unit": "MINUTES"}
    for calendar in scenario["resource_calendars"]:
        for period in calendar["time_periods"]:
            period["probability"] = 0.4
        calendar["workload_ratio"] = [
            {**period, "probability": 0.7} for period in calendar["time_periods"]
        ]
    imported = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )
    assert imported.status_code == 200, imported.text

    run = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs",
        json={
            "model": imported.json()["model"],
            "current_bpmn_xml": bpmn,
            "total_cases": 50,
            "scenario_name": "Scenario FUZZY",
        },
    )

    assert run.status_code == 200, run.text
    payload = sent[0].scenario.model_dump(mode="json")["payload"]
    assert payload["model_type"] == "FUZZY"
    assert payload["granule_size"] == {"value": 60, "time_unit": "MINUTES"}
    for calendar in payload["resource_calendars"]:
        assert {p["probability"] for p in calendar["time_periods"]} == {0.4}
        assert {p["probability"] for p in calendar["workload_ratio"]} == {0.7}


@pytest.mark.skipif(
    not os.environ.get("DELIR_TEST_PROSIMOS_URL"),
    reason="serve il runner Prosimos 2.1 dello stack: DELIR_TEST_PROSIMOS_URL=$PROSIMOS_BASE_URL",
)
def test_the_simod_fuzzy_scenario_runs_on_the_stack_runner(client):
    """CAL-01: lo scenario FUZZY scoperto da SIMOD fa il percorso del prodotto.

    Import dal server, run in coda, runner Prosimos 2.1 vero, esito letto dal database.
    """
    from tests.simulation.simod_fuzzy import simod_fuzzy

    scenario, bpmn = simod_fuzzy()
    bpmn_model_id = _bpmn_model_id(client)

    imported = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )
    assert imported.status_code == 200, imported.text
    run = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs",
        json={
            "model": imported.json()["model"],
            "current_bpmn_xml": bpmn,
            "total_cases": 100,
            "seed": 7,
            "scenario_name": "SIMOD FUZZY",
        },
    )
    assert run.status_code == 200, run.text

    # TestClient esegue il drenaggio della coda prima di rispondere: il run e' finito.
    finished = client.get(f"/v1/workspace/simulation-runs/{run.json()['id']}").json()
    assert finished["status"] == "completed", finished["error"]
    assert finished["result"]["EngineVersion"].startswith("2.1")
    sent = finished["scenario"]
    assert sent["model_type"] == "FUZZY"
    assert sent["granule_size"] == scenario["granule_size"]
    assert {c["id"] for c in sent["resource_calendars"]} <= {
        c["id"] for c in scenario["resource_calendars"]
    }
    assert finished["summary"]["casesCompleted"] == 100


def test_a_process_that_cannot_finish_is_a_400_with_a_stable_code(client):
    """VAL-01: lo scenario SIMOD di AcademicCredentials (ciclo a uscita 0, G3)."""
    bpmn_model_id = _bpmn_model_id(client)
    folder = ROOT / "tests" / "simulation" / "benchmark" / "g3" / "discovered" / "AcademicCredentials_diff"
    scenario = json.loads((folder / "AcademicCredentials.json").read_text(encoding="utf-8"))
    bpmn = (folder / "AcademicCredentials.bpmn").read_text(encoding="utf-8")

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/prosimos-import",
        json={"scenario": scenario, "current_bpmn_xml": bpmn},
    )

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "process_cannot_finish"
    assert "«Avanzar recepcion documentos»" in error["message"]
    assert "node_" not in error["message"]
    assert "node_59fc62b1-3b4e-4c11-ba7b-1cab3392cdaa" in error["detail"]


def test_a_run_of_a_model_that_cannot_finish_has_the_same_stable_code(client):
    """VAL-01 al run: una bozza o un what-if che non finirebbe non arriva al motore."""
    bpmn_model_id = _bpmn_model_id(client)
    fixtures = ROOT / "e2e" / "fixtures" / "val-01"
    bpmn = (fixtures / "loop.bpmn").read_text(encoding="utf-8")
    model = json.loads((fixtures / "loop-fixed.import.json").read_text(encoding="utf-8"))["model"]
    for gateway in model["gateways"]:
        for branch in gateway["branches"]:
            branch["probability"] = 1.0 if branch["flow_id"] == "F_again" else 0.0

    response = client.post(
        f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-model-runs",
        json={"model": model, "current_bpmn_xml": bpmn, "total_cases": 10, "scenario_name": "pratiche"},
    )

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "process_cannot_finish"
    assert "«Controlla documenti»" in error["message"]
    assert "G_complete" in error["detail"]
