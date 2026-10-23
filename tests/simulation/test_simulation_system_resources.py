"""SIM-09b: sistemi e macchine come risorse."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.ir.from_request import ALWAYS_CALENDAR_ID, STANDARD_CALENDAR_ID
from backend.simulation.ir.model import Resource, ResourceShift
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
NIGHT = {"id": "night", "name": "Notte", "periods": [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "20:00", "end": "23:00"}]}


def _request(*resources: dict, calendars: list | None = None) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        tasks=[{"element_id": "T_receive", "mean_seconds": 600, "resource_id": "ops"},
               {"element_id": "T_approve", "mean_seconds": 60, "resource_id": "erp"},
               {"element_id": "T_pay", "mean_seconds": 600, "resource_id": "ops"}],
        resources=[{"id": "ops", "name": "Operatore", "amount": 2, "cost_per_hour": 30}, *resources],
        calendars=calendars or [],
    )


def _resources(scenario) -> dict:
    return {r["id"]: r for pool in scenario.model["pools"] for r in pool["resources"]}


def test_a_system_without_calendar_works_always_and_keeps_its_kind():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"id": "erp", "name": "Sistema ERP", "amount": 20, "cost_per_hour": 0, "kind": "system"}))

    resources = _resources(scenario)
    assert resources["erp"]["kind"] == "system" and resources["erp"]["calendar_id"] == ALWAYS_CALENDAR_ID
    assert resources["ops"]["kind"] == "person" and resources["ops"]["calendar_id"] == STANDARD_CALENDAR_ID
    always = next(c for c in scenario.payload["resource_calendars"] if c["id"] == ALWAYS_CALENDAR_ID)
    assert always["time_periods"] == [{"from": "MONDAY", "to": "SUNDAY", "beginTime": "00:00:00.000", "endTime": "23:59:59.999"}]


def test_a_system_with_its_own_calendar_keeps_it():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"id": "erp", "name": "Batch notturno", "amount": 1, "cost_per_hour": 0, "kind": "system", "calendar_id": "night"},
        calendars=[NIGHT]))
    assert _resources(scenario)["erp"]["calendar_id"] == "night"
    assert all(c["id"] != ALWAYS_CALENDAR_ID for c in scenario.payload["resource_calendars"])


def test_without_systems_nothing_changes():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
        {"id": "erp", "name": "Approvatore", "amount": 1, "cost_per_hour": 50}))
    assert all(c["id"] != ALWAYS_CALENDAR_ID for c in scenario.model["calendars"])


def test_a_system_with_shifts_is_refused_with_the_reason():
    with pytest.raises(ValueError, match="Un sistema non ha turni"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(
            {"id": "erp", "name": "Sistema ERP", "amount": 1, "cost_per_hour": 0, "kind": "system",
             "shifts": [{"amount": 1, "calendar_id": "night"}]}, calendars=[NIGHT]))
    with pytest.raises(ValidationError):
        Resource(id="erp", name="ERP", cost_per_hour=0, amount=1, calendar_id="c", kind="system",
                 shifts=(ResourceShift(amount=1, calendar_id="c"),))


def test_the_always_calendar_id_is_reserved():
    taken = {"id": ALWAYS_CALENDAR_ID, "name": "Mio", "periods": NIGHT["periods"]}
    with pytest.raises(ValueError, match="distinti"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request(calendars=[taken]))
