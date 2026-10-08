"""Il log di un run si scarica come event log canonico, con seed e impronta."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.simulation.models import ProsimosSimulationResult
from tests.simulation.test_simulation_replay import MINIMAL_BPMN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prosimos"
LOG = (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")
STATS = json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def _model(client, name: str) -> tuple[str, str]:
    cl = client.post("/v1/workspace/clients", json={"name": name}).json()
    pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": f"{name} P"}).json()
    ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": f"{name} Proc"}).json()
    return ps["id"], ps["bpmn_model_id"]


def _run(client, monkeypatch, model_id: str, *, log: str | None, payload: dict | None = None) -> int:
    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(payload or STATS), event_log_csv=log)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    run = client.post(
        f"/v1/workspace/bpmn-models/{model_id}/simulation-runs",
        json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN},
    ).json()
    return run["id"]


def test_the_csv_export_carries_seed_engine_and_a_hash_of_its_bytes(client, monkeypatch):
    _, model_id = _model(client, "ExpCsv")
    run_id = _run(client, monkeypatch, model_id, log=LOG, payload={**STATS, "Seed": 42, "EngineVersion": "2.1.0"})

    response = client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f"simulation-run-{run_id}.csv" in response.headers["content-disposition"]
    assert response.headers["x-simulation-seed"] == "42"
    assert response.headers["x-simulation-engine-version"] == "2.1.0"
    assert response.headers["x-content-sha256"] == hashlib.sha256(response.content).hexdigest()
    assert response.text.splitlines()[0] == "case_id,activity,enable_time,start_time,end_time,resource,role"
    assert len(response.text.splitlines()) == len(LOG.strip().splitlines())


def test_the_xes_export_is_the_same_run_in_the_standard_format(client, monkeypatch):
    _, model_id = _model(client, "ExpXes")
    run_id = _run(client, monkeypatch, model_id, log=LOG, payload={**STATS, "Seed": 7})

    response = client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log", params={"format": "xes"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert 'key="deliR:seed" value="7"' in response.text
    assert response.headers["x-content-sha256"] == hashlib.sha256(response.content).hexdigest()


def test_two_downloads_of_the_same_run_are_byte_identical(client, monkeypatch):
    _, model_id = _model(client, "ExpTwice")
    run_id = _run(client, monkeypatch, model_id, log=LOG)
    url = f"/v1/workspace/simulation-runs/{run_id}/event-log"

    assert client.get(url).content == client.get(url).content


def test_a_run_without_a_log_or_an_unknown_run_answers_404(client, monkeypatch):
    _, model_id = _model(client, "ExpNone")
    run_id = _run(client, monkeypatch, model_id, log=None)

    assert client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log").status_code == 404
    assert client.get("/v1/workspace/simulation-runs/999999999/event-log").status_code == 404


def test_an_unknown_format_is_refused(client, monkeypatch):
    _, model_id = _model(client, "ExpFmt")
    run_id = _run(client, monkeypatch, model_id, log=LOG)

    assert client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log", params={"format": "xlsx"}).status_code == 422


def test_deleting_the_process_removes_the_stored_log(client, monkeypatch):
    process_id, model_id = _model(client, "ExpPurge")
    run_id = _run(client, monkeypatch, model_id, log=LOG)
    assert client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log").status_code == 200

    assert client.delete(f"/v1/workspace/processes/{process_id}").status_code in (200, 204)

    assert client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log").status_code == 404


def test_the_downloaded_log_is_reimported_by_the_wizard_with_the_same_kpis(client, monkeypatch):
    process_id, model_id = _model(client, "ExpRoundTrip")
    run_id = _run(client, monkeypatch, model_id, log=LOG)
    simulated = client.get(f"/v1/workspace/simulation-runs/{run_id}").json()["summary"]
    exported = client.get(f"/v1/workspace/simulation-runs/{run_id}/event-log")

    uploaded = client.post(
        f"/v1/workspace/processes/{process_id}/event-logs",
        files={"file": ("simulation-run.csv", exported.content, "text/csv")},
    ).json()
    mapping = {
        "case_id": ["case_id"],
        "activity": ["activity"],
        "enable": "enable_time",
        "start": "start_time",
        "end": "end_time",
        "resource": "resource",
        "role": "role",
        "timestamps": {"timezone": "UTC"},
    }
    analysis = client.post(f"/v1/workspace/event-logs/{uploaded['id']}/mapping", json={"mapping": mapping})

    assert analysis.status_code == 200, analysis.text
    real = analysis.json()["summary"]
    assert real["source"] == "real"
    for kpi in ("casesCompleted", "cycle", "waiting", "processing", "throughputPerHour"):
        assert kpi in simulated, kpi
        assert real[kpi] == simulated[kpi], kpi
