"""SIM-01/02: le sei distribuzioni di Prosimos 2.1 e i calendari per risorsa, dalla richiesta al motore."""

import pytest
from pydantic import ValidationError

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    SimCalendarConfig,
    SimCalendarPeriodConfig,
    SimResourceConfig,
    SimTaskConfig,
)
from backend.simulation.advisor import _service_rate
from backend.simulation.ir import compile_for_prosimos, model_from_request
from backend.simulation.ir.from_request import STANDARD_CALENDAR_ID
from backend.simulation.scenario_builder import describe_scenario_template, parse_bpmn_for_simulation
from tests.simulation.test_simulation_ir import BPMN

TASKS, GATEWAYS = parse_bpmn_for_simulation(BPMN)
RESOURCES = [
    SimResourceConfig(id="back", name="Back office", cost_per_hour=30, amount=2),
    SimResourceConfig(id="night", name="Turno notte", cost_per_hour=40, amount=1, calendar_id="cal-night"),
]
NIGHT = SimCalendarConfig(
    id="cal-night",
    name="Turno notte",
    periods=[
        SimCalendarPeriodConfig(from_day="MONDAY", to_day="FRIDAY", begin="22:00", end="23:59:59"),
        SimCalendarPeriodConfig(from_day="TUESDAY", to_day="SATURDAY", begin="00:00", end="06:00"),
    ],
)


def _scenario(*tasks: SimTaskConfig, resources=None, calendars=None) -> dict:
    by_id = {task.element_id: task for task in tasks}
    configs = [
        by_id.get(task.id) or SimTaskConfig(element_id=task.id, mean_seconds=600, resource_id="back")
        for task in TASKS
    ]
    request = CreateSimulationRunRequest(
        resources=resources if resources is not None else RESOURCES,
        calendars=calendars if calendars is not None else [NIGHT],
        tasks=configs,
    )
    return compile_for_prosimos(model_from_request(request, TASKS, GATEWAYS))


def _duration(scenario: dict, task_id: str) -> tuple[str, list[float]]:
    row = next(r for r in scenario["task_resource_distribution"] if r["task_id"] == task_id)
    dist = row["resources"][0]
    return dist["distribution_name"], [p["value"] for p in dist["distribution_params"]]


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="fixed", resource_id="back"), ("fix", [600])),
        (
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="expon", resource_id="back",
                          min_seconds=60, max_seconds=3600),
            ("expon", [600, 60, 3600]),
        ),
        (
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="uniform", resource_id="back",
                          min_seconds=300, max_seconds=900),
            ("uniform", [300, 900]),
        ),
        (
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="norm", resource_id="back", std_seconds=120),
            ("norm", [600, 120, 240, 960]),
        ),
        (
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="lognorm", resource_id="back",
                          std_seconds=200, min_seconds=0, max_seconds=3000),
            ("lognorm", [600, 40_000, 0, 3000]),
        ),
        (
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="gamma", resource_id="back", std_seconds=100),
            ("gamma", [600, 10_000, 300, 900]),
        ),
    ],
    ids=["fissa", "esponenziale", "uniforme", "normale", "lognormale", "gamma"],
)
def test_each_distribution_reaches_the_engine_with_its_parameters(task, expected):
    assert _duration(_scenario(task), "T_pay") == expected


def test_missing_parameters_keep_the_historic_assumptions():
    task = SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="lognorm", resource_id="back")

    # dev. std al 10% della media, limiti a +-3 sigma
    assert _duration(_scenario(task), "T_pay") == ("lognorm", [600, 3600, 420, 780])


def test_triangular_weibull_and_beta_are_not_accepted():
    for name in ("triang", "weibull_min", "beta"):
        with pytest.raises(ValidationError):
            SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution=name)


@pytest.mark.parametrize(
    ("task", "message"),
    [
        (SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="uniform", resource_id="back", min_seconds=300),
         "indica minimo e massimo"),
        (SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="uniform", resource_id="back",
                       min_seconds=900, max_seconds=300), "minore del massimo"),
        (SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="norm", resource_id="back",
                       min_seconds=700, max_seconds=900), "la media deve stare fra minimo e massimo"),
    ],
)
def test_inconsistent_parameters_are_refused_with_a_readable_reason(task, message):
    with pytest.raises(ValueError, match=message):
        _scenario(task)


def test_each_resource_works_on_its_own_calendar():
    scenario = _scenario()

    calendars = {r["id"]: r["calendar"] for p in scenario["resource_profiles"] for r in p["resource_list"]}
    assert calendars == {"back": STANDARD_CALENDAR_ID, "night": "cal-night"}
    night = next(c for c in scenario["resource_calendars"] if c["id"] == "cal-night")
    assert night["time_periods"] == [
        {"from": "MONDAY", "to": "FRIDAY", "beginTime": "22:00:00.000", "endTime": "23:59:59"},
        {"from": "TUESDAY", "to": "SATURDAY", "beginTime": "00:00:00.000", "endTime": "06:00:00.000"},
    ]
    # Gli arrivi restano sul calendario standard.
    assert scenario["arrival_time_calendar"][0]["beginTime"] == "09:00:00.000"


@pytest.mark.parametrize(
    ("resources", "calendars", "message"),
    [
        (RESOURCES, [], "Calendari inesistenti"),
        (RESOURCES, [NIGHT, NIGHT], "identificativi distinti"),
        (RESOURCES[:1], [NIGHT.model_copy(update={"id": STANDARD_CALENDAR_ID})], "identificativi distinti"),
        (
            RESOURCES,
            [NIGHT.model_copy(update={"periods": [SimCalendarPeriodConfig(from_day="MONDAY", to_day="FRIDAY", begin="22:00", end="06:00")]})],
            "passa la mezzanotte",
        ),
    ],
    ids=["calendario-assente", "duplicato", "standard-ridefinito", "mezzanotte"],
)
def test_calendar_errors_name_the_problem(resources, calendars, message):
    with pytest.raises(ValueError, match=message):
        _scenario(resources=resources, calendars=calendars)


def test_the_template_shows_the_standard_calendar():
    template = describe_scenario_template(BPMN)

    assert template.standard_calendar is not None
    assert template.standard_calendar.id == STANDARD_CALENDAR_ID
    assert [(p.from_day, p.to_day, p.begin, p.end) for p in template.standard_calendar.periods] == [
        ("MONDAY", "FRIDAY", "09:00", "17:00")
    ]


def test_the_advisor_reads_the_mean_of_a_uniform_duration():
    task = SimTaskConfig(element_id="T_pay", mean_seconds=600, distribution="uniform", resource_id="back",
                         min_seconds=300, max_seconds=900)

    assert _service_rate(_scenario(task), "T_pay") == pytest.approx(1 / 600)
