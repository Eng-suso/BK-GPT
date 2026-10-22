"""SIM-28: previsto contro osservato per un'alternativa implementata, via API.

Il log reale ha casi prima e dopo il 10 gennaio: prima un caso dura 2 ore, dopo
1 ora. L'alternativa prevedeva un cycle time del 40% piu' corto (intervallo
dal -50% al -30%): l'osservato e' -50%, dentro l'intervallo, con 10 punti di
errore.
"""

import pytest

from backend.eventlog.model import CanonicalEvent, EventLog
from backend.eventlog.periods import cases_started
from backend.schemas.simulation_scenarios import PredictedKpi
from backend.simulation.outcomes import compare, observed_value
from tests.simulation.test_simulation_scenarios import PLUS_ONE_APPROVER, _url, _with_baseline

MAPPING = {"case_id": ["Caso"], "activity": ["Attivita"], "start": "Inizio", "end": "Fine",
           "timestamps": {"pattern": "%Y-%m-%d %H:%M"}}


def _csv() -> bytes:
    rows = ["Caso,Attivita,Inizio,Fine"]
    for day, hours in ((5, 2), (6, 2), (7, 2), (12, 1), (13, 1), (14, 1)):
        rows.append(f"C{day},Ricevi,2026-01-{day:02d} 09:00,2026-01-{day:02d} 09:30")
        rows.append(f"C{day},Approva,2026-01-{day:02d} 09:30,2026-01-{day:02d} {9 + hours:02d}:00")
    return ("\n".join(rows) + "\n").encode()


def _log(api_client, model_id: str, name: str = "erp.csv") -> str:
    process_id = api_client.get(f"/v1/workspace/bpmn-models/{model_id}").json()["process_id"]
    uploaded = api_client.post(f"/v1/workspace/processes/{process_id}/event-logs",
                               files={"file": (name, _csv(), "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    log_id = uploaded.json()["id"]
    mapped = api_client.post(f"/v1/workspace/event-logs/{log_id}/mapping", json={"mapping": MAPPING})
    assert mapped.status_code == 200, mapped.text
    return log_id


def _alternative(api_client, model_id: str) -> int:
    _with_baseline(api_client, model_id)
    created = api_client.post(_url(model_id), json={"name": "+1 approvatore", "patch": PLUS_ONE_APPROVER})
    assert created.status_code == 200, created.text
    return created.json()["alternatives"][0]["id"]


def _outcome(log_id: str, **extra) -> dict:
    return {
        "implemented_on": "2026-01-10",
        "before_event_log_id": log_id,
        "after_event_log_id": log_id,
        "as_is_run_id": 1,
        "alternative_run_id": 2,
        "predicted": {"cycle": {"as_is": 10_000, "alternative": 6_000, "half": 1_000}},
        **extra,
    }


def test_an_implemented_alternative_records_predicted_against_observed(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    scenario_id = _alternative(api_client, model_id)
    log_id = _log(api_client, model_id)

    response = api_client.put(_url(model_id, f"/{scenario_id}/outcome"), json=_outcome(log_id))

    assert response.status_code == 200, response.text
    scenario = response.json()["alternatives"][0]
    outcome = scenario["outcome"]
    assert outcome["implemented_on"] == "2026-01-10"
    assert (outcome["before"]["cases"], outcome["after"]["cases"]) == (3, 3)
    [cycle] = outcome["kpis"]
    assert cycle["kpi"] == "cycle"
    assert cycle["predicted_change"] == pytest.approx(-0.4)
    assert (cycle["predicted_low"], cycle["predicted_high"]) == (pytest.approx(-0.5), pytest.approx(-0.3))
    assert (cycle["before"], cycle["after"]) == (pytest.approx(7200), pytest.approx(3600))
    assert cycle["observed_change"] == pytest.approx(-0.5)
    assert cycle["error"] == pytest.approx(-0.1)
    assert cycle["within"] is True
    # L'esito non cambia cio' che lo scenario simula: la revisione resta.
    assert scenario["revision"] == 1
    assert api_client.get(_url(model_id)).json()["alternatives"][0]["outcome"] == outcome

    removed = api_client.delete(_url(model_id, f"/{scenario_id}/outcome"))
    assert removed.json()["alternatives"][0]["outcome"] is None


def test_the_outcome_is_refused_without_cases_on_one_side_or_on_the_as_is(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    scenario_id = _alternative(api_client, model_id)
    log_id = _log(api_client, model_id)

    too_early = api_client.put(_url(model_id, f"/{scenario_id}/outcome"), json=_outcome(log_id, implemented_on="2025-12-01"))
    baseline_id = api_client.get(_url(model_id)).json()["baseline"]["id"]
    on_as_is = api_client.put(_url(model_id, f"/{baseline_id}/outcome"), json=_outcome(log_id))

    assert too_early.status_code == 400
    assert "nessun caso inizia prima del 01/12/2025" in too_early.json()["error"]["message"]
    assert on_as_is.status_code == 400


def test_a_log_of_another_process_is_refused(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    scenario_id = _alternative(api_client, model_id)
    other_log = _log(api_client, new_bpmn_model())

    response = api_client.put(_url(model_id, f"/{scenario_id}/outcome"), json=_outcome(other_log))

    assert response.status_code == 400
    assert "non è di questo processo" in response.json()["error"]["message"]


def test_a_case_belongs_to_the_period_it_starts_in():
    from datetime import date, datetime

    log = EventLog(origin="real", events=(
        CanonicalEvent(case_id="a", activity="X", start=datetime(2026, 1, 9, 23, 0), end=datetime(2026, 1, 10, 2, 0)),
        CanonicalEvent(case_id="b", activity="X", start=datetime(2026, 1, 10, 9, 0), end=datetime(2026, 1, 10, 10, 0)),
    ))

    assert {e.case_id for e in cases_started(log, before=date(2026, 1, 10)).events} == {"a"}
    assert {e.case_id for e in cases_started(log, since=date(2026, 1, 10)).events} == {"b"}


def test_what_the_log_does_not_know_stays_unknown():
    assert observed_value({"cost": None}, "costPerCase") is None
    result = compare("costPerCase", PredictedKpi(as_is=50, alternative=40), None, None)
    assert (result.predicted_change, result.observed_change, result.error, result.within) == (-0.2, None, None, None)
    # Senza ripetizioni la previsione non ha intervallo: niente "dentro" o "fuori".
    assert compare("cycle", PredictedKpi(as_is=100, alternative=80), 100, 70).within is None


def test_a_scenario_from_before_the_outcome_still_reads(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _alternative(api_client, model_id)
    assert api_client.get(_url(model_id)).json()["alternatives"][0]["outcome"] is None
