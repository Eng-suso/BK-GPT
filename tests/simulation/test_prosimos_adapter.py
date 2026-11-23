"""Contratto dell'adapter verso il runner Prosimos (B0: parita' del motore)."""

import asyncio
import json

import httpx
import pytest

from backend.settings import settings
from backend.simulation.models import ProsimosScenario, ProsimosSimulationRequest
from backend.simulation.prosimos_adapter import ProsimosError, run_prosimos_simulation

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN = (
    f'<definitions xmlns="{NS}"><process id="P"><startEvent id="S"/><task id="T" name="Lavora"/><endEvent id="E"/>'
    '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/><sequenceFlow id="F2" sourceRef="T" targetRef="E"/>'
    "</process></definitions>"
)
LOG = "case_id,activity,enable_time,start_time,end_time,resource\n0,Lavora,2026-01-05 09:00:00+00:00,2026-01-05 09:00:00+00:00,2026-01-05 09:10:00+00:00,R_0\n"
STATS = {key: json.dumps("[]") for key in ("ResourceUtilization", "IndividualTaskStatistics", "OverallScenarioStatistics")}


def _request() -> ProsimosSimulationRequest:
    return ProsimosSimulationRequest(
        bpmn_xml=BPMN, scenario=ProsimosScenario(payload={}, task_count=1, gateway_count=0), total_cases=1, seed=7,
    )


def _engine(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real = httpx.AsyncClient
    monkeypatch.setattr("backend.simulation.prosimos_adapter.httpx.AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(record)}))
    return seen


def _run():
    return asyncio.run(run_prosimos_simulation(_request()))


def test_the_inline_log_is_used_without_a_second_call(monkeypatch):
    seen = _engine(monkeypatch, lambda r: httpx.Response(200, json={
        **STATS, "EngineVersion": "2.1.0", "Seed": 7, "LogsFilename": "logs_x.csv", "EventLogCsv": LOG,
    }))

    result = _run()

    assert result.event_log_csv == LOG
    assert "EventLogCsv" not in result.payload  # il log non finisce nel risultato salvato
    assert [r.url.path for r in seen] == ["/api/simulate"]
    body = seen[0].content.decode("utf-8", "replace")
    assert 'name="inlineLog"' in body and 'name="seed"' in body


def test_an_older_runner_without_inline_log_still_works_by_download(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/simulationFile":
            return httpx.Response(200, text=LOG)
        return httpx.Response(200, json={**STATS, "EngineVersion": "2.1.0", "LogsFilename": "logs_x.csv"})

    seen = _engine(monkeypatch, handler)

    assert _run().event_log_csv == LOG
    assert [r.url.path for r in seen] == ["/api/simulate", "/api/simulationFile"]


@pytest.mark.parametrize("version", [None, "", "1.2.6", "unknown"])
def test_an_engine_that_is_not_the_2x_runner_is_refused(monkeypatch, version):
    payload = {**STATS, "LogsFilename": "logs_x.csv", "EventLogCsv": LOG}
    if version is not None:
        payload["EngineVersion"] = version
    _engine(monkeypatch, lambda r: httpx.Response(200, json=payload))

    with pytest.raises(ProsimosError, match="non e' il runner DeliR"):
        _run()


def test_a_run_whose_log_cannot_be_read_fails_instead_of_completing_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/simulationFile":
            return httpx.Response(404, json={"errorMessage": "file non trovato o scaduto"})
        return httpx.Response(200, json={**STATS, "EngineVersion": "2.1.0", "LogsFilename": "logs_x.csv"})

    _engine(monkeypatch, handler)

    with pytest.raises(ProsimosError, match="log degli eventi non e' arrivato"):
        _run()


def test_the_shared_token_goes_on_every_call(monkeypatch):
    monkeypatch.setattr(settings, "prosimos_api_token", "s3cret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/simulationFile":
            return httpx.Response(200, text=LOG)
        return httpx.Response(200, json={**STATS, "EngineVersion": "2.1.0", "LogsFilename": "logs_x.csv"})

    seen = _engine(monkeypatch, handler)
    _run()

    assert {r.headers.get("authorization") for r in seen} == {"Bearer s3cret"}


def test_no_token_means_no_authorization_header(monkeypatch):
    monkeypatch.setattr(settings, "prosimos_api_token", "")
    seen = _engine(monkeypatch, lambda r: httpx.Response(200, json={**STATS, "EngineVersion": "2.1.0", "EventLogCsv": LOG}))
    _run()

    assert "authorization" not in seen[0].headers


def test_a_timeout_says_what_to_do(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    _engine(monkeypatch, handler)

    with pytest.raises(ProsimosError, match="non ha risposto entro"):
        _run()
