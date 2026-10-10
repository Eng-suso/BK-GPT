"""SIM-13: l'obiettivo di servizio dello scenario e il suo esito sul run."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.simulation.models import ProsimosSimulationResult
from backend.simulation.sla import sla_outcome
from tests.simulation.test_simulation_replay import MINIMAL_BPMN

HEADER = "case_id,activity,enable_time,start_time,end_time,resource"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prosimos"
LOG = (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")
STATS = json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))


def _at(hour: int) -> str:
    return f"2026-01-05 {hour:02d}:00:00.000000+00:00"


def _row(case: str, activity: str, start_hour: int, end_hour: int) -> str:
    return f"{case},{activity},{_at(start_hour)},{_at(start_hour)},{_at(end_hour)},Ufficio"


def _log(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_the_share_of_cases_within_the_target_decides_the_outcome():
    log = _log(
        _row("1", "Ricevi", 9, 10), _row("1", "Paga", 10, 11),  # 2 ore
        _row("2", "Ricevi", 9, 10), _row("2", "Paga", 10, 14),  # 5 ore
        _row("3", "Ricevi", 9, 10),                              # 1 ora
        _row("4", "Ricevi", 9, 12),                              # 3 ore, esattamente il target
    )
    outcome = sla_outcome(log, target_seconds=3 * 3600, share=0.8)
    assert outcome == {"target_seconds": 10800, "share_target": 0.8, "share_within": 0.75,
                       "cases": 4, "late_cases": 1, "met": False}
    assert sla_outcome(log, target_seconds=3 * 3600, share=0.75)["met"] is True


def test_the_run_summary_carries_the_outcome_of_the_scenario_sla(monkeypatch):
    from backend.app import app

    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(STATS), event_log_csv=LOG)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "Sla"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "Sla P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Sla Proc"}).json()
        run = client.post(
            f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
            json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN, "sla": {"target_seconds": 86_400, "share": 0.9}},
        ).json()
        summary = client.get(f"/v1/workspace/simulation-runs/{run['id']}").json()["summary"]

    sla = summary["sla"]
    assert sla["target_seconds"] == 86_400 and sla["share_target"] == 0.9
    assert sla["cases"] > 0 and 0 <= sla["share_within"] <= 1
    assert sla["met"] == (sla["share_within"] >= 0.9)


def test_without_an_sla_the_summary_has_none(monkeypatch):
    from backend.app import app

    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(STATS), event_log_csv=LOG)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "NoSla"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "NoSla P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "NoSla Proc"}).json()
        run = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                          json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN}).json()
        summary = client.get(f"/v1/workspace/simulation-runs/{run['id']}").json()["summary"]
    assert "sla" not in summary
