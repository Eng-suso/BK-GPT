"""SIM-08b: il ritmo degli arrivi cambia con il mese."""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.horizon import horizon_cases
from backend.simulation.ir.model import MonthFactor
from backend.simulation.scenario_builder import build_prosimos_scenario
from tests.simulation.test_simulation_horizon import MONDAY, _model

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
PEAK = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00", "mean_seconds": 300}
DECEMBER_UP_AUGUST_DOWN = [{"month": 12, "factor": 1.4}, {"month": 8, "factor": 0.5}]


def _request(arrival: dict) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        arrival=arrival,
    )


def test_months_reach_the_runner_with_the_bands_and_stay_in_the_model():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"mean_seconds": 900, "bands": [PEAK], "months": DECEMBER_UP_AUGUST_DOWN}))

    assert scenario.payload["delir_arrival_months"] == {"12": 1.4, "8": 0.5}
    assert len(scenario.payload["delir_arrival_bands"]) == 1
    assert scenario.model["arrival"]["months"] == [{"month": 12, "factor": 1.4}, {"month": 8, "factor": 0.5}]


def test_without_bands_exponential_arrivals_become_bands_of_their_calendar():
    # Lo stesso Poisson: la media fra due arrivi su ogni periodo del calendario standard.
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"mean_seconds": 900, "months": DECEMBER_UP_AUGUST_DOWN}))

    bands = scenario.payload["delir_arrival_bands"]
    assert bands and all(band["meanSeconds"] == 900.0 for band in bands)
    assert [b["beginTime"] for b in bands] == [p["beginTime"] for p in scenario.payload["arrival_time_calendar"]]
    # Il modello resta quello del consulente: niente fasce inventate.
    assert scenario.model["arrival"]["bands"] == []


def test_without_months_nothing_changes():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"mean_seconds": 900}))
    assert "delir_arrival_bands" not in scenario.payload and "delir_arrival_months" not in scenario.payload


@pytest.mark.parametrize(("arrival", "message"), [
    ({"mean_seconds": 900, "distribution": "norm", "months": DECEMBER_UP_AUGUST_DOWN}, "esponenziali"),
    ({"mean_seconds": 900, "months": [{"month": 12, "factor": 1.4}, {"month": 12, "factor": 2}]}, "duplicato"),
])
def test_months_that_do_not_fit_are_refused_with_the_reason(arrival, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival))


@pytest.mark.parametrize("month", [{"month": 0, "factor": 1}, {"month": 13, "factor": 1}, {"month": 5, "factor": 0}])
def test_a_month_out_of_range_is_a_validation_error(month):
    with pytest.raises(ValueError):
        _request({"mean_seconds": 900, "months": [month]})


def test_the_cases_of_a_period_follow_the_month_factor():
    base = _model()
    busy_january = base.model_copy(update={"arrival": base.arrival.model_copy(update={"months": (MonthFactor(month=1, factor=2),)})})
    # La settimana del 5 gennaio al doppio: 80 arrivi diventano 160, senza le 5 aperture del motore; x1,5 + 30.
    assert horizon_cases(base, MONDAY, 7) == 158
    assert horizon_cases(busy_january, MONDAY, 7) == 270


def test_an_engine_that_ignores_the_months_is_refused(monkeypatch):
    import asyncio
    import json

    import httpx

    from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
    from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation

    def handler(request: httpx.Request) -> httpx.Response:
        # Un runner di prima di SIM-08b: le fasce si', i mesi no.
        return httpx.Response(200, json={"OverallScenarioStatistics": json.dumps("[]"), "LogsFilename": "l.csv", "ArrivalBands": 1})

    real = httpx.AsyncClient
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request({"mean_seconds": 900, "bands": [PEAK], "months": DECEMBER_UP_AUGUST_DOWN}))
    request = ProsimosSimulationRequest(
        bpmn_xml=BPMN, scenario=ProsimosScenario(payload=scenario.payload, task_count=3, gateway_count=1), total_cases=3)
    with pytest.raises(ProsimosError, match="per mese"):
        asyncio.run(run_prosimos_simulation(request))
