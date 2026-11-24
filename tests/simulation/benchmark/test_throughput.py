"""B6: le parti dello script di carico che non hanno bisogno dello stack."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.scenario_builder import build_prosimos_scenario
from tests.simulation.benchmark.throughput import CASES, REPLICAS, SEED, phases, same_results, table, whatif_request


def test_the_fixed_whatif_is_a_valid_panel_request_for_every_task():
    body = whatif_request()
    request = CreateSimulationRunRequest(**body)
    assert (request.total_cases, request.replications, request.seed) == (CASES, REPLICAS, SEED)

    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(body["current_bpmn_xml"]), request=request)
    assert scenario.task_count == 17
    # Le 5 decisioni del processo, con le probabilita' del paper; gli altri 4 gateway hanno un ramo solo.
    assert scenario.gateway_count == 5
    assert scenario.payload["arrival_time_distribution"] == {"distribution_name": "fix", "distribution_params": [{"value": 900.0}]}


def _log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "api.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_phases_come_from_the_worker_line_of_each_run(tmp_path):
    log = _log(tmp_path, [
        "2026-11-24 INFO backend.simulation.service simulazione 7: in coda 1.000 s, motore 2.000 s, analisi 0.500 s",
        "2026-11-24 INFO backend.simulation.service simulazione 8: in coda 3.000 s, motore 1.000 s, analisi 0.300 s",
        "2026-11-24 INFO backend.simulation.service simulazione 9: in coda 9.000 s, motore 9.000 s, analisi 9.000 s",
    ])
    measured = phases(log, [7, 8])
    assert measured["in coda"] == {"mean": 2.0, "max": 3.0}
    assert measured["motore"]["mean"] == 1.5


def test_other_lines_are_ignored_and_a_rerun_counts_its_last_line(tmp_path):
    log = _log(tmp_path, [
        "ERROR backend.simulation.service simulazione 7: analisi del risultato fallita",
        "INFO backend.simulation.service simulazione 7: in coda 0.500 s, motore 9.000 s",
        "INFO backend.simulation.service simulazione 7: motore 2.000 s, analisi 0.100 s",
    ])
    assert phases(log, [7]) == {"motore": {"mean": 2.0, "max": 2.0}, "analisi": {"mean": 0.1, "max": 0.1}}


def test_a_run_without_its_line_is_an_error(tmp_path):
    log = _log(tmp_path, ["simulazione 7: motore 2.000 s"])
    with pytest.raises(RuntimeError, match="fasi mancanti"):
        phases(log, [7, 8])


def _result(workers: int, total: float, kpi: str = "a") -> dict:
    return {
        "workers": workers, "round": 1, "total_s": total, "runs_per_minute": REPLICAS / total * 60,
        "accepted_s": 0.1, "completed_s": total - 1, "kpi_read_s": total - 0.5,
        "phases": {"motore": {"mean": 1.5, "max": 2.0}},
        "fingerprints": {"1": {"seed": SEED, "kpi": kpi, "event_log": "b"}},
    }


def test_different_results_are_named_by_workers_round_and_replica():
    assert same_results([_result(1, 20), _result(4, 10)], None) == []
    assert same_results([_result(1, 20), _result(4, 10, kpi="x")], None) == ["4 worker, giro 1, ripetizione 1"]
    reference = {"1": {"seed": SEED, "kpi": "x", "event_log": "b"}}
    assert same_results([_result(1, 20)], reference) == ["1 worker, giro 1, ripetizione 1"]


def test_the_table_marks_the_target_on_the_total():
    rows = table([_result(1, 59.9), _result(1, 60.0)]).splitlines()
    assert rows[-2].endswith("| raggiunta |")
    assert rows[-1].endswith("| no |")
