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
