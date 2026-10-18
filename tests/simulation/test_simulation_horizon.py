"""SIM-03: un periodo da simulare invece di un numero di casi."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.simulation.horizon import horizon_cases, horizon_end, horizon_start, within_horizon
from backend.simulation.ir.model import (
    Activity,
    Arrival,
    ArrivalBand,
    Assignment,
    Calendar,
    CalendarPeriod,
    Exponential,
    Fixed,
    Resource,
    ResourcePool,
    SimulationModel,
)
from backend.simulation.log_processor import LogEvent, parse_prosimos_log, process_prosimos_log
from backend.simulation.models import ProsimosSimulationResult
from backend.simulation.sla import sla_outcome
from tests.simulation.test_simulation_replay import MINIMAL_BPMN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prosimos"
LOG = (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")
STATS = json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))
# Il log di prova va dal 5 gennaio 2026 (lunedi') alle 9 al 6 gennaio alle 13:45.
MONDAY = "2026-01-05T00:00:00+00:00"


def _model(*, bands: tuple[ArrivalBand, ...] = ()) -> SimulationModel:
    office = Calendar(id="office", name="Ufficio", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),))
    return SimulationModel(
        arrival=Arrival(interarrival=Exponential(mean=1800, minimum=0, maximum=18000), calendar_id="office", bands=bands),
        calendars=(office,),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=1, calendar_id="office"),)),),
        activities=(Activity(element_id="T", assignments=(Assignment(resource_id="ops", duration=Fixed(value=600)),)),),
    )


def test_the_cases_cover_the_period_from_the_arrival_rhythm_and_calendar():
    # Una settimana: 5 giorni x 8 ore aperte / 30 minuti = 80 arrivi, +5 aperture; x1,5 + 30.
    assert horizon_cases(_model(), MONDAY, 7) == 158
    # Il sabato e la domenica non aggiungono arrivi.
    assert horizon_cases(_model(), "2026-01-10T00:00:00+00:00", 2) == 30


def test_with_bands_the_cases_follow_the_bands():
    morning = ArrivalBand(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="12:00:00", mean_seconds=600)
    # 5 x 3 ore / 10 minuti = 90 arrivi; x1,5 + 30.
    assert horizon_cases(_model(bands=(morning,)), MONDAY, 7) == 165


def test_a_period_too_long_for_the_arrival_rhythm_is_refused():
    fast = _model().model_copy(update={"arrival": Arrival(
        interarrival=Exponential(mean=10, minimum=0, maximum=100), calendar_id="office")})
    with pytest.raises(ValueError, match="Accorcia il periodo"):
        horizon_cases(fast, MONDAY, 366)


def test_the_period_starts_when_asked_or_at_midnight_today():
    assert horizon_start(MONDAY) == MONDAY
    noon = datetime(2026, 10, 17, 12, 34, 56, tzinfo=UTC)
    assert horizon_start(None, today=noon) == "2026-10-17T00:00:00+00:00"
    assert horizon_end(MONDAY, 1) == datetime(2026, 1, 6, tzinfo=UTC).timestamp()


def _event(case: str, enable_hour: float, end_hour: float) -> LogEvent:
    base = datetime(2026, 1, 5, tzinfo=UTC).timestamp()
    return LogEvent(case_id=case, activity="A", enable=base + enable_hour * 3600, start=base + enable_hour * 3600,
                    end=base + end_hour * 3600, resource="r")


def test_at_the_end_of_the_period_cases_are_completed_open_or_not_yet_arrived():
    events = [
        _event("done", 1, 2), _event("done", 2, 3),
        _event("open", 5, 7), _event("open", 7, 30),  # finisce dopo la fine del periodo
        _event("later", 25, 26),                       # arriva dopo
    ]
    completed, arrived, outcome = within_horizon(events, horizon_end(MONDAY, 1), 1)
    assert {e.case_id for e in completed} == {"done"}
    assert {e.case_id for e in arrived} == {"done", "open"}
    assert (outcome.arrived_cases, outcome.completed_cases, outcome.open_cases, outcome.covered) == (2, 1, 1, True)
    # Senza arrivi dopo la fine, la copertura del periodo non e' garantita.
    assert within_horizon(events[:4], horizon_end(MONDAY, 1), 1)[2].covered is False


def test_the_summary_measures_the_cases_completed_in_the_period():
    full, _ = process_prosimos_log(LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS)
    summary, replay = process_prosimos_log(
        LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS,
        horizon=(horizon_end(MONDAY, 1), 1),
    )
    period = summary["horizon"]
    assert period["covered"] is True and 0 < period["completedCases"] < full["casesCompleted"]
    assert summary["casesCompleted"] == period["completedCases"]
    assert period["arrivedCases"] == period["completedCases"] + period["openCases"]
    # Il costo del run si attribuisce ai casi misurati: meno casi, meno costo.
    assert 0 < summary["cost"]["total"] < full["cost"]["total"]
    assert "warmup" not in summary
    assert replay["meta"]["totalCases"] == period["arrivedCases"]


def test_the_service_objective_judges_the_same_cases():
    horizon = (horizon_end(MONDAY, 1), 1)
    summary, _ = process_prosimos_log(LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS,
                                      horizon=horizon)
    outcome = sla_outcome(LOG, target_seconds=3600, share=0.9, horizon=horizon)
    assert outcome is not None and outcome.cases == summary["horizon"]["completedCases"]


def test_a_period_shorter_than_the_first_completion_has_nothing_to_measure():
    first = min(e.end for e in parse_prosimos_log(LOG))
    with pytest.raises(ValueError, match="nessun caso completato"):
        process_prosimos_log(LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS,
                             horizon=(first - 1, 1))


def test_a_warmup_that_swallows_every_completed_case_is_named():
    with pytest.raises(ValueError, match="il riscaldamento esclude tutti i casi"):
        process_prosimos_log(LOG, normalized_bpmn_xml=MINIMAL_BPMN, scenario_payload={}, prosimos_stats=STATS,
                             horizon=(horizon_end(MONDAY, 1), 1), warmup_cases=1000)


def test_a_run_with_a_period_estimates_its_cases_and_reports_the_period(monkeypatch):
    from backend.app import app

    seen = {}

    async def fake_run(request):
        seen["total_cases"], seen["start_date"] = request.total_cases, request.start_date
        return ProsimosSimulationResult(payload=dict(STATS), event_log_csv=LOG)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)
    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "Horizon"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "Horizon P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Horizon Proc"}).json()
        run = client.post(
            f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
            json={"total_cases": 10, "current_bpmn_xml": MINIMAL_BPMN, "start_date": MONDAY, "horizon_days": 1,
                  "arrival_interval_seconds": 1800},
        ).json()
        body = client.get(f"/v1/workspace/simulation-runs/{run['id']}").json()
        exported = client.get(f"/v1/workspace/simulation-runs/{run['id']}/event-log").text

    # Calendario standard lun-ven 9-17, un giorno: 8 ore / 30 minuti = 16 arrivi, +1 apertura; x1,5 + 30.
    assert seen == {"total_cases": 56, "start_date": MONDAY}
    assert body["request"]["total_cases"] == 56
    assert body["summary"]["horizon"]["days"] == 1
    # L'export e' il log osservato nel periodo: niente dopo la fine, niente casi arrivati dopo.
    rows = [line.split(",") for line in exported.strip().splitlines()[1:]]
    header = exported.splitlines()[0].split(",")
    end_at = header.index(next(h for h in header if h.startswith("end")))
    assert rows and all(row[end_at] < "2026-01-06" for row in rows)
    assert len({row[0] for row in rows}) <= body["summary"]["horizon"]["arrivedCases"]


def test_an_invalid_period_is_refused():
    from backend.app import app

    with TestClient(app) as client:
        cl = client.post("/v1/workspace/clients", json={"name": "BadHorizon"}).json()
        pr = client.post("/v1/workspace/projects", json={"client_id": cl["id"], "name": "BadHorizon P"}).json()
        ps = client.post(f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "BadHorizon Proc"}).json()
        response = client.post(f"/v1/workspace/bpmn-models/{ps['bpmn_model_id']}/simulation-runs",
                               json={"current_bpmn_xml": MINIMAL_BPMN, "horizon_days": 0})
    assert response.status_code == 422
