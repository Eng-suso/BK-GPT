"""A2-3: gli arrivi dei casi con la loro distribuzione e il loro calendario.

Il pannello scenario manda ``arrival`` nella richiesta v1: la distribuzione del
tempo fra due arrivi (le stesse sei delle durate) e il calendario in cui i casi
arrivano. Senza ``arrival`` resta l'esponenziale storica sull'intervallo medio.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
MORNINGS = {"id": "mornings", "name": "Mattine", "periods": [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00"}]}


def _request(**overrides) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        **overrides,
    )


def test_arrivals_keep_their_distribution_and_calendar():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        calendars=[MORNINGS],
        arrival={"mean_seconds": 900, "distribution": "uniform", "min_seconds": 600, "max_seconds": 1200, "calendar_id": "mornings"},
    ))

    arrival = scenario.model["arrival"]
    assert arrival["interarrival"] == {"kind": "uniform", "minimum": 600.0, "maximum": 1200.0}
    assert arrival["calendar_id"] == "mornings"
    assert arrival["provenance"]["origin"] == "manual"
    assert scenario.payload["arrival_time_distribution"]["distribution_name"] == "uniform"
    assert scenario.payload["arrival_time_calendar"][0]["beginTime"].startswith("09:00")


def test_without_arrival_the_historical_exponential_stays():
    plain = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival_interval_seconds=1200))
    same = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival={"mean_seconds": 1200}))

    assert plain.model["arrival"] == same.model["arrival"]
    assert plain.model["arrival"]["interarrival"] == {"kind": "exponential", "mean": 1200.0, "minimum": 0.0, "maximum": 12000.0}


@pytest.mark.parametrize(
    ("arrival", "message"),
    [
        ({"mean_seconds": 900, "calendar_id": "ghost"}, "calendario degli arrivi non esiste più"),
        ({"mean_seconds": 900, "distribution": "uniform"}, "Arrivi: .*indica minimo e massimo"),
    ],
)
def test_arrivals_that_do_not_fit_are_refused_with_the_reason(arrival, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival=arrival))


def test_the_run_keeps_the_arrivals_in_the_model_the_inspector_reads(api_client, new_bpmn_model, fake_engine):
    created = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request(calendars=[MORNINGS], arrival={"mean_seconds": 600, "distribution": "fixed", "calendar_id": "mornings"})
              .model_dump(mode="json"), "current_bpmn_xml": BPMN},
    )
    assert created.status_code == 200, created.text

    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    assert model["arrival"]["interarrival"] == {"kind": "fixed", "value": 600.0}
    assert model["arrival"]["calendar_id"] == "mornings"


def test_an_unknown_arrival_calendar_is_a_400(api_client, new_bpmn_model, fake_engine):
    response = api_client.post(
        f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
        json={**_request(arrival={"mean_seconds": 600, "calendar_id": "ghost"}).model_dump(mode="json"), "current_bpmn_xml": BPMN},
    )
    assert response.status_code == 400
    assert "calendario degli arrivi" in response.json()["error"]["message"]
    assert fake_engine == []


# --- SIM-08: un ritmo per fascia oraria ------------------------------------------

PEAK = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00", "mean_seconds": 300}
QUIET = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "14:00", "end": "17:00", "mean_seconds": 1800}


def test_arrival_bands_reach_the_runner_section_and_the_model():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival={"mean_seconds": 900, "bands": [PEAK, QUIET]}))

    assert scenario.payload["delir_arrival_bands"] == [
        {"from": "MONDAY", "to": "FRIDAY", "beginTime": "09:00:00.000", "endTime": "12:00:00.000", "meanSeconds": 300.0},
        {"from": "MONDAY", "to": "FRIDAY", "beginTime": "14:00:00.000", "endTime": "17:00:00.000", "meanSeconds": 1800.0},
    ]
    # Il calendario degli arrivi segue le fasce: fuori non arriva nessuno.
    assert [p["beginTime"] for p in scenario.payload["arrival_time_calendar"]] == ["09:00:00.000", "14:00:00.000"]
    assert [b["mean_seconds"] for b in scenario.model["arrival"]["bands"]] == [300.0, 1800.0]


def test_without_bands_the_scenario_has_no_runner_section():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival={"mean_seconds": 900}))
    assert "delir_arrival_bands" not in scenario.payload


@pytest.mark.parametrize(("bands", "message"), [
    ([PEAK, {**PEAK, "begin": "11:00", "end": "13:00"}], "si sovrappongono"),
    ([{**PEAK, "begin": "12:00", "end": "09:00"}], "passa la mezzanotte"),
])
def test_bands_that_do_not_fit_are_refused_with_the_reason(bands, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival={"mean_seconds": 900, "bands": bands}))


def test_an_engine_that_ignores_the_bands_is_refused(monkeypatch):
    import asyncio
    import json

    import httpx

    from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
    from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation

    def handler(request: httpx.Request) -> httpx.Response:
        # Come il microservizio 1.2.6: nessun ArrivalBands nella risposta.
        return httpx.Response(200, json={"OverallScenarioStatistics": json.dumps("[]"), "LogsFilename": "logs_x.csv"})

    real = httpx.AsyncClient
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival={"mean_seconds": 900, "bands": [PEAK]}))
    request = ProsimosSimulationRequest(
        bpmn_xml=BPMN, scenario=ProsimosScenario(payload=scenario.payload, task_count=3, gateway_count=1), total_cases=3)
    with pytest.raises(ProsimosError, match="fasce degli arrivi"):
        asyncio.run(run_prosimos_simulation(request))


# --- SIM-33: la fascia di arrivo come attributo del caso ----------------------------

def _band_attribute(values=("Fascia 1", "Fascia 2")) -> dict:
    share = 1 / len(values)
    return {"case_attributes": [{"name": "fascia", "options": [{"value": v, "probability": share} for v in values]}]}


def test_the_band_attribute_reaches_the_runner_and_the_model():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        arrival={"mean_seconds": 900, "bands": [PEAK, QUIET], "band_attribute": "fascia"},
        model_patch=_band_attribute(),
    ))
    assert scenario.payload["delir_arrival_band_attribute"] == "fascia"
    assert scenario.model["arrival"]["band_attribute"] == "fascia"


@pytest.mark.parametrize(("arrival", "patch", "message"), [
    ({"mean_seconds": 900, "bands": [PEAK, QUIET], "band_attribute": "fascia"}, None, "fascia non c'e'"),
    ({"mean_seconds": 900, "bands": [PEAK, QUIET], "band_attribute": "fascia"}, _band_attribute(("Mattina", "Pomeriggio")), "Fascia 1, Fascia 2"),
    ({"mean_seconds": 900, "band_attribute": "fascia"}, _band_attribute(("Fascia 1",)), "richiede delle fasce"),
])
def test_a_band_attribute_that_does_not_match_the_bands_is_refused(arrival, patch, message):
    with pytest.raises(ValueError, match=message):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(arrival=arrival, **({"model_patch": patch} if patch else {})))
