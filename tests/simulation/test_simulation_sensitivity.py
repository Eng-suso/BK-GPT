"""SIM-25: il tornado di sensitivita', una ipotesi incerta alla volta."""

import pytest

from backend.schemas.simulation import CreateSensitivityRequest, CreateSimulationRunRequest, SensitivityFactor
from backend.simulation.sensitivity import perturb
from tests.simulation.test_simulation_replay import MINIMAL_BPMN


def _request(rich: bool = True, **extra) -> CreateSimulationRunRequest:
    review = {"element_id": "Task_R", "mean_seconds": 300, "distribution": "uniform", "min_seconds": 200, "max_seconds": 400}
    if rich:
        review |= {"other_assignments": [{"resource_id": "Senior", "mean_seconds": 200}],
                   "duration_by": {"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 100}]}}
    return CreateSimulationRunRequest(**{
        "total_cases": 10,
        "current_bpmn_xml": MINIMAL_BPMN,
        "tasks": [
            {"element_id": "Task_A", "mean_seconds": 600, "std_seconds": 60, "distribution": "norm"},
            review,
        ],
        "gateways": [{"element_id": "Gateway_1", "branches": [
            {"flow_id": "Flow_4", "probability": 0.7}, {"flow_id": "Flow_5", "probability": 0.3},
        ]}],
        **extra,
    })


def _duration(element_id: str = "Task_R") -> SensitivityFactor:
    return SensitivityFactor(kind="duration", element_id=element_id, label="Revisione")


def test_a_duration_scales_mean_spread_bounds_other_roles_and_categories():
    task = perturb(_request(), _duration(), "high", 0.2).tasks[1]
    assert task.mean_seconds == pytest.approx(360)
    assert (task.min_seconds, task.max_seconds) == (pytest.approx(240), pytest.approx(480))
    assert task.other_assignments[0].mean_seconds == pytest.approx(240)
    assert task.duration_by.variants[0].mean_seconds == pytest.approx(120)


def test_only_the_chosen_activity_moves():
    request = _request()
    moved = perturb(request, _duration(), "low", 0.2)
    assert moved.tasks[0] == request.tasks[0]
    assert moved.tasks[1].mean_seconds == pytest.approx(240)
    assert request.tasks[1].mean_seconds == 300  # la richiesta di partenza non cambia


def test_arrivals_scale_the_time_between_two_arrivals_bands_included():
    simple = perturb(_request(arrival_interval_seconds=1000), SensitivityFactor(kind="arrival"), "low", 0.2)
    assert simple.arrival_interval_seconds == 800

    banded = _request(arrival={"mean_seconds": 600, "distribution": "expon", "bands": [
        {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00", "mean_seconds": 300},
    ]})
    moved = perturb(banded, SensitivityFactor(kind="arrival"), "high", 0.2).arrival
    assert moved.mean_seconds == pytest.approx(720)
    assert moved.bands[0].mean_seconds == pytest.approx(360)


def test_a_gateway_moves_its_most_likely_branch_and_keeps_the_sum_at_one():
    factor = SensitivityFactor(kind="gateway", element_id="Gateway_1", label="Esito")
    high = perturb(_request(), factor, "high", 0.2).gateways[0].branches
    assert [b.probability for b in high] == [pytest.approx(0.84), pytest.approx(0.16)]

    capped = _request(gateways=[{"element_id": "Gateway_1", "branches": [
        {"flow_id": "Flow_4", "probability": 0.9}, {"flow_id": "Flow_5", "probability": 0.1},
    ]}])
    branches = perturb(capped, factor, "high", 0.2).gateways[0].branches
    assert [b.probability for b in branches] == [pytest.approx(1.0), pytest.approx(0.0)]


def test_an_assumption_missing_from_the_scenario_is_refused_with_its_name():
    with pytest.raises(ValueError, match="Controllo"):
        perturb(_request(), SensitivityFactor(kind="duration", element_id="Task_X", label="Controllo"), "low", 0.2)
    with pytest.raises(ValueError, match="Decisione"):
        perturb(_request(gateways=[]), SensitivityFactor(kind="gateway", element_id="Gateway_1", label="Decisione"), "low", 0.2)


def test_the_request_refuses_a_repeated_assumption_and_an_arrival_with_an_element():
    with pytest.raises(ValueError, match="due volte"):
        CreateSensitivityRequest(base=_request(), factors=[_duration(), _duration()])
    with pytest.raises(ValueError, match="arrivi"):
        SensitivityFactor(kind="arrival", element_id="Task_A")
    with pytest.raises(ValueError):
        SensitivityFactor(kind="duration")


# --- API ------------------------------------------------------------------ #


def _url(new_bpmn_model) -> tuple[str, str]:
    model = new_bpmn_model()
    return (f"/v1/workspace/bpmn-models/{model}/simulation-sensitivity",
            f"/v1/workspace/bpmn-models/{model}/simulation-runs")


def _body(**extra) -> dict:
    return {
        "base": _request(rich=False, seed=42, scenario_name="AS-IS").model_dump(exclude_none=True),
        "factors": [
            {"kind": "duration", "element_id": "Task_R", "label": "Revisione"},
            {"kind": "arrival", "label": "Arrivi"},
        ],
        **extra,
    }


def test_a_study_is_the_central_run_and_two_variants_per_assumption_on_one_seed(api_client, new_bpmn_model, fake_engine):
    url, runs_url = _url(new_bpmn_model)
    response = api_client.post(url, json=_body())
    assert response.status_code == 200, response.text
    runs = response.json()

    assert len(runs) == 5
    assert len({run["request"]["sensitivity_study"] for run in runs}) == 1
    assert runs[0]["request"]["sensitivity"] is None
    marks = [(r["request"]["sensitivity"]["element_id"], r["request"]["sensitivity"]["direction"]) for r in runs[1:]]
    assert marks == [("Task_R", "low"), ("Task_R", "high"), (None, "low"), (None, "high")]
    assert [r["scenario_name"] for r in runs] == [
        "AS-IS", "AS-IS · Revisione -20%", "AS-IS · Revisione +20%", "AS-IS · Arrivi -20%", "AS-IS · Arrivi +20%",
    ]
    assert {request.seed for request in fake_engine} == {42}
    assert len(api_client.get(runs_url).json()) == 5


def test_a_study_ignores_replications_and_marks_sent_by_the_client(api_client, new_bpmn_model, fake_engine):
    url, _ = _url(new_bpmn_model)
    body = _body()
    body["base"].update({"replications": 5, "sensitivity_study": "altrui", "replication_group": "altrui"})
    runs = api_client.post(url, json=body).json()
    assert len(runs) == 5
    assert "altrui" not in {r["request"]["sensitivity_study"] for r in runs}
    assert {r["request"]["replication_group"] for r in runs} == {None}


def test_a_single_run_drops_a_study_sent_by_the_client(api_client, new_bpmn_model, fake_engine):
    _, runs_url = _url(new_bpmn_model)
    run = api_client.post(runs_url, json={"total_cases": 10, "current_bpmn_xml": MINIMAL_BPMN,
                                          "sensitivity_study": "altrui"}).json()
    assert run["request"]["sensitivity_study"] is None


def test_a_study_that_does_not_fit_the_queue_is_refused_whole(api_client, new_bpmn_model, fake_engine, monkeypatch):
    from backend.settings import settings

    monkeypatch.setattr(settings, "simulation_max_queued_runs", 4)
    url, runs_url = _url(new_bpmn_model)
    assert api_client.post(url, json=_body()).status_code == 429
    assert api_client.get(runs_url).json() == []


def test_an_unknown_assumption_is_a_400_and_queues_nothing(api_client, new_bpmn_model, fake_engine):
    url, runs_url = _url(new_bpmn_model)
    response = api_client.post(url, json=_body(factors=[{"kind": "duration", "element_id": "Task_X", "label": "Controllo"}]))
    assert response.status_code == 400
    assert "Controllo" in response.json()["error"]["message"]
    assert api_client.get(runs_url).json() == []


def test_with_a_period_every_variant_keeps_the_start_and_reestimates_its_cases(api_client, new_bpmn_model, fake_engine):
    url, _ = _url(new_bpmn_model)
    body = _body(factors=[{"kind": "arrival", "label": "Arrivi"}])
    body["base"].update({"horizon_days": 5, "start_date": "2026-10-05T00:00:00+00:00", "arrival_interval_seconds": 1800})
    runs = api_client.post(url, json=body).json()
    assert len({r["request"]["start_date"] for r in runs}) == 1
    central, faster, slower = (r["request"]["total_cases"] for r in runs)
    assert faster > central > slower
