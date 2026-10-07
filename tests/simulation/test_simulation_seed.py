"""Il seed va dalla richiesta al runner, e torna nel risultato del run."""

import asyncio
import json

import httpx
import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import run_prosimos_simulation
from backend.simulation.service import _derive_idempotency_key

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN = (
    f'<definitions xmlns="{NS}"><process id="P">'
    '<startEvent id="S"/><task id="T" name="Lavora"/><endEvent id="E"/>'
    '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/>'
    '<sequenceFlow id="F2" sourceRef="T" targetRef="E"/>'
    "</process></definitions>"
)
SCENARIO = ProsimosScenario(payload={"resource_profiles": []}, task_count=1, gateway_count=0)


def _runner(seen: list[dict]):
    """Un runner finto: registra il form ricevuto e risponde come il runner DeliR."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/simulate":
            body = request.content.decode("latin-1")
            seen.append({"seed_sent": 'name="seed"' in body, "body": body})
            return httpx.Response(200, json={
                "OverallScenarioStatistics": json.dumps(json.dumps([{"KPI": "cycle_time"}])),
                "LogsFilename": "logs_x.csv",
                "Seed": 42,
                "EngineVersion": "2.1.0",
            })
        return httpx.Response(200, text="case_id,activity,enable_time,start_time,end_time,resource\n")

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    return factory


def _run(monkeypatch, seed):
    seen: list[dict] = []
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient", _runner(seen))
    result = asyncio.run(run_prosimos_simulation(
        ProsimosSimulationRequest(bpmn_xml=BPMN, scenario=SCENARIO, total_cases=3, seed=seed)
    ))
    return seen[0], result


def test_the_seed_is_sent_to_the_runner(monkeypatch):
    sent, _ = _run(monkeypatch, 7)

    assert sent["seed_sent"]
    assert 'name="seed"\r\n\r\n7\r\n' in sent["body"]


def test_without_a_seed_the_form_does_not_carry_one(monkeypatch):
    sent, _ = _run(monkeypatch, None)

    assert not sent["seed_sent"]


def test_the_result_keeps_the_seed_and_engine_that_produced_it(monkeypatch):
    _, result = _run(monkeypatch, None)

    assert result.payload["Seed"] == 42
    assert result.payload["EngineVersion"] == "2.1.0"
    assert result.payload["OverallScenarioStatistics"] == [{"KPI": "cycle_time"}]


def test_the_result_keeps_the_start_date_used_when_the_request_had_none(monkeypatch):
    """Il seed da solo non basta: il calendario dipende dalla data di inizio."""
    sent, result = _run(monkeypatch, 7)

    start = result.payload["StartDate"]
    assert start
    assert f'name="startDate"\r\n\r\n{start}\r\n' in sent["body"]


def _key(**request):
    return _derive_idempotency_key(
        bpmn_model_id="m",
        bpmn_xml=BPMN,
        scenario=SCENARIO,
        request=CreateSimulationRunRequest(**request),
    )


def test_a_different_seed_is_a_different_run():
    assert _key(seed=1) != _key(seed=2)
    assert _key(seed=1) == _key(seed=1)


@pytest.mark.parametrize("seed", [-1, 2**32])
def test_a_seed_outside_the_engine_range_is_refused(seed):
    with pytest.raises(ValueError):
        CreateSimulationRunRequest(seed=seed)
