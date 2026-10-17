"""SIM-30: organico che cambia nel tempo, con turni di rinforzo.

"Due operatori tutto il giorno, due in piu' dalle 9 alle 12": la risorsa ha un
turno sul calendario 9-12. Il motore non conosce organici variabili: il turno
diventa una risorsa in piu', con le stesse attivita' e le stesse durate.
"""

from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.scenario_builder import build_prosimos_scenario

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
MORNINGS = {"id": "mornings", "name": "Mattine", "periods": [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00"}]}


def _request(shifts: list[dict], calendars: list[dict] | None = None) -> CreateSimulationRunRequest:
    return CreateSimulationRunRequest(
        total_cases=20,
        calendars=calendars if calendars is not None else [MORNINGS],
        resources=[{"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 2, "shifts": shifts}],
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "ops"},
            {"element_id": "T_approve", "mean_seconds": 1200, "resource_id": "ops", "distribution": "fixed"},
            {"element_id": "T_pay", "mean_seconds": 600, "resource_id": "ops"},
        ],
    )


def test_a_shift_becomes_a_resource_with_the_same_work_and_durations():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request([{"amount": 2, "calendar_id": "mornings"}]))

    resources = {r["id"]: r for p in scenario.payload["resource_profiles"] for r in p["resource_list"]}
    shift = resources["ops__shift_1"]
    assert (shift["name"], shift["amount"], shift["calendar"], shift["cost_per_hour"]) == ("Operatore · turno 2", 2, "mornings", "30.0")
    assert shift["assignedTasks"] == resources["ops"]["assignedTasks"]
    approve = next(t for t in scenario.payload["task_resource_distribution"] if t["task_id"] == "T_approve")
    assert [r["resource_id"] for r in approve["resources"]] == ["ops", "ops__shift_1"]
    assert approve["resources"][0]["distribution_params"] == approve["resources"][1]["distribution_params"]
    # Il calendario del turno arriva al motore.
    assert "mornings" in {c["id"] for c in scenario.payload["resource_calendars"]}
    # Il run conserva la risorsa con il suo turno, non la copia.
    ops = scenario.model["pools"][0]["resources"][0]
    assert ops["shifts"] == [{"amount": 2, "calendar_id": "mornings", "provenance": {"origin": "manual", "confidence": None, "sources": [], "note": None}}]
    assert len(scenario.model["pools"][0]["resources"]) == 1


def test_without_shifts_nothing_changes():
    scenario = build_prosimos_scenario(bpmn_xml=BPMN, request=_request([]))
    assert [r["id"] for p in scenario.payload["resource_profiles"] for r in p["resource_list"]] == ["ops"]


def test_a_shift_on_an_unknown_calendar_is_refused():
    with pytest.raises(ValueError, match="Calendari inesistenti"):
        build_prosimos_scenario(bpmn_xml=BPMN, request=_request([{"amount": 1, "calendar_id": "nights"}]))
