"""SIM-10: i costi fissi per esecuzione e per caso, sommati al costo delle risorse."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.simulation.costs import FixedCosts, add_fixed_costs
from backend.simulation.models import ProsimosSimulationResult
from tests.simulation.test_simulation_replay import MINIMAL_BPMN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prosimos"
LOG = (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")
STATS = json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))


def test_fixed_costs_join_the_total_with_their_breakdown():
    summary = {
        "casesCompleted": 10,
        "cost": {"total": 500.0, "perCase": 50.0},
        "byActivity": [{"el": "A", "count": 10}, {"el": "B", "count": 4}],
    }
    out = add_fixed_costs(summary, FixedCosts(per_execution={"B": 25.0}, per_case=3.0))
    assert out["byActivity"][1]["fixedCost"] == 100.0
    assert "fixedCost" not in out["byActivity"][0]
    assert out["cost"]["breakdown"] == {"resources": 500.0, "activities": 100.0, "cases": 30.0}
    assert out["cost"]["total"] == 630.0
    assert out["cost"]["perCase"] == 63.0


def test_no_fixed_costs_is_falsy():
    assert not FixedCosts()
    assert FixedCosts(per_case=1.0)


def test_the_run_summary_includes_the_fixed_costs(monkeypatch):
    from backend.app import app

    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(STATS), event_log_csv=LOG)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "Cost"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "Cost P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Cost Proc"}).json()
        plain = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                            json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN, "seed": 1}).json()
        fixed = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                            json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN, "seed": 1, "case_fixed_cost": 2.5}).json()
        base = client.get(f"/v1/workspace/simulation-runs/{plain['id']}").json()["summary"]["cost"]
        cost = client.get(f"/v1/workspace/simulation-runs/{fixed['id']}").json()["summary"]["cost"]

    assert fixed["id"] != plain["id"]
    assert "breakdown" not in base
    assert cost["breakdown"]["resources"] == base["total"]
    assert cost["breakdown"]["cases"] > 0
    assert cost["total"] == base["total"] + cost["breakdown"]["cases"]
