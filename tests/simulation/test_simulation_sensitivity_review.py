"""SIM-25: l'agente di review legge i risultati del processo, non le varianti di sensitivita'."""

import json

from backend.graphs.task_review import read_review_simulations


def test_the_review_reads_scenario_results_and_skips_sensitivity_variants(monkeypatch):
    runs = [{"id": 9 - i, "status": "completed", "scenario_name": f"Base · variante {i}",
             "request": {"sensitivity_study": "s", "sensitivity": {"kind": "arrival", "direction": "high", "delta": 0.2}}}
            for i in range(6)]
    runs.append({"id": 3, "status": "completed", "scenario_name": "Base", "request": {"sensitivity_study": "s"}})
    monkeypatch.setattr("backend.simulation.storage.list_simulation_runs", lambda _model: runs)

    read = json.loads(read_review_simulations.func(state={"bpmn_model_id": "m"}))
    assert [run["id"] for run in read] == [3]
