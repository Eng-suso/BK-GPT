"""SIM-33b: la durata di un'attivita' cambia con l'ora in cui inizia.

Il pannello manda ``duration_windows`` nella config del task; il modello IR le
conserva sull'attivita' (anche sulle copie per categoria) e lo scenario del
motore le porta nella sezione DeliR che il runner applica.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
AFTERNOON = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "16:00", "end": "17:00", "factor": 1.3}


def _request(approve: dict | None = None, **overrides) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 600, **(approve or {})},
            {"element_id": "T_pay", "mean_seconds": 600},
        ],
        **overrides,
    )


def test_windows_reach_the_model_and_the_runner_section():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"duration_windows": [AFTERNOON]}))

    approve = next(a for a in scenario.model["activities"] if a["element_id"] == "T_approve")
    [window] = approve["duration_windows"]
    assert (window["from_day"], window["to_day"], window["begin"], window["end"], window["factor"]) == (
        "MONDAY", "FRIDAY", "16:00:00.000", "17:00:00.000", 1.3)
    assert window["provenance"]["origin"] == "manual"
    assert scenario.payload["delir_duration_windows"] == {"T_approve": [
        {"from": "MONDAY", "to": "FRIDAY", "beginTime": "16:00:00.000", "endTime": "17:00:00.000", "factor": 1.3},
    ]}


def test_without_windows_the_scenario_has_no_runner_section():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request())

    assert "delir_duration_windows" not in scenario.payload
    assert all(a["duration_windows"] == [] for a in scenario.model["activities"])


def test_the_copies_of_a_duration_by_category_keep_the_windows():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"duration_windows": [AFTERNOON], "duration_by": {"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 300}]}},
        model_patch={"case_attributes": [{"name": "tipo", "options": [{"value": "premium", "probability": 0.4}, {"value": "altro", "probability": 0.6}]}]},
    ))

    windows = scenario.payload["delir_duration_windows"]
    assert len(windows) == 2
    assert "T_approve" in windows
    assert all(w == windows["T_approve"] for w in windows.values())


@pytest.mark.parametrize(
    ("windows", "message"),
    [
        ([AFTERNOON, {**AFTERNOON, "begin": "16:30", "end": "16:45"}], "si sovrappongono"),
        ([{**AFTERNOON, "begin": "17:00", "end": "16:00"}], "va diviso in due"),
    ],
)
def test_windows_that_do_not_fit_are_refused_with_the_reason(windows, message):
    with pytest.raises(ValueError, match=f"fasce orarie della durata: .*{message}"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"duration_windows": windows}))


@pytest.mark.parametrize("factor", [0, -1, 10.5])
def test_a_factor_out_of_range_is_refused_by_the_request(factor):
    with pytest.raises(ValueError):
        _request({"duration_windows": [{**AFTERNOON, "factor": factor}]})


def test_an_engine_that_ignores_the_windows_is_refused(monkeypatch):
    from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
    from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation

    def handler(request: httpx.Request) -> httpx.Response:
        # Un motore senza la patch del runner: nessun DurationWindows nella risposta.
        return httpx.Response(200, json={"OverallScenarioStatistics": json.dumps("[]"), "LogsFilename": "logs_x.csv"})

    real = httpx.AsyncClient
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"duration_windows": [AFTERNOON]}))
    request = ProsimosSimulationRequest(
        bpmn_xml=BPMN, scenario=ProsimosScenario(payload=scenario.payload, task_count=3, gateway_count=1), total_cases=3)
    with pytest.raises(ProsimosError, match="durate per fascia oraria"):
        asyncio.run(run_prosimos_simulation(request))
