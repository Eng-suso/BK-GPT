"""SIM-03: i primi casi trovano il sistema vuoto e restano fuori dai KPI."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.simulation.log_processor import after_warmup, parse_prosimos_log, process_prosimos_log
from backend.simulation.models import ProsimosSimulationResult
from tests.simulation.test_simulation_replay import MINIMAL_BPMN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prosimos"
LOG = (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")
STATS = json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))


def _summary(warmup: int) -> dict:
    summary, _replay = process_prosimos_log(
        LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS, warmup_cases=warmup)
    return summary


def test_the_first_cases_by_arrival_are_left_out():
    events = parse_prosimos_log(LOG)
    cases = {e.case_id for e in events}
    kept = {e.case_id for e in after_warmup(events, 5)}
    first = min(events, key=lambda e: e.enable).case_id
    assert len(kept) == len(cases) - 5
    assert first not in kept
    assert after_warmup(events, 0) is events


def test_the_summary_measures_only_the_cases_after_the_warmup():
    full, warm = _summary(0), _summary(5)
    assert warm["casesCompleted"] == full["casesCompleted"] - 5
    assert warm["warmup"] == {"excludedCases": 5, "measuredCases": warm["casesCompleted"]}
    assert "warmup" not in full
    # Il costo dell'intero run si attribuisce ai casi misurati: meno casi, meno costo.
    assert 0 < warm["cost"]["total"] < full["cost"]["total"]


def test_a_warmup_that_leaves_no_case_is_refused(monkeypatch):
    from backend.app import app

    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "Warm"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "Warm P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Warm Proc"}).json()
        response = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                               json={"total_cases": 10, "warmup_cases": 10, "current_bpmn_xml": MINIMAL_BPMN})
    assert response.status_code == 400
    assert "almeno un caso da misurare" in response.json()["error"]["message"]


def test_the_run_summary_reports_the_warmup(monkeypatch):
    from backend.app import app

    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(STATS), event_log_csv=LOG)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "Warm2"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "Warm2 P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Warm2 Proc"}).json()
        run = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                          json={"total_cases": 60, "warmup_cases": 5, "current_bpmn_xml": MINIMAL_BPMN}).json()
        summary = client.get(f"/v1/workspace/simulation-runs/{run['id']}").json()["summary"]
    assert summary["warmup"]["excludedCases"] == 5
