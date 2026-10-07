"""SIM-37: il contratto di run sull'IR - patch, baseline, validazione sul BPMN, API."""

import pytest
from pydantic import ValidationError

from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CalendarPeriod,
    CaseAttribute,
    Condition,
    DiscreteOption,
    Exponential,
    Gateway,
    LogNormal,
    Normal,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
)
from backend.simulation.ir.patch import ModelPatch, apply_patch

OFFICE = Calendar(
    id="office",
    name="Ufficio",
    periods=(CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),),
)
NIGHT = Calendar(
    id="night",
    name="Notte",
    periods=(
        CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="22:00:00", end="23:59:59"),
        CalendarPeriod(from_day="TUESDAY", to_day="SATURDAY", begin="00:00:00", end="06:00:00"),
    ),
)


def _when(attribute, operator, value) -> Condition:
    return Condition(any_of=((Rule(attribute=attribute, operator=operator, value=value),),))


def _baseline() -> SimulationModel:
    return SimulationModel(
        arrival=Arrival(interarrival=Exponential(mean=1800, minimum=0, maximum=18000), calendar_id="office"),
        calendars=(OFFICE,),
        pools=(
            ResourcePool(
                id="p",
                name="Ufficio",
                resources=(Resource(id="ops", name="Operatore", cost_per_hour=30, amount=2, calendar_id="office"),),
            ),
        ),
        activities=(
            Activity(element_id="Task_A", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=600, std=60, minimum=420, maximum=780)),)),
            Activity(element_id="Task_B", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=900, std=90, minimum=630, maximum=1170)),)),
        ),
        gateways=(
            Gateway(element_id="Gateway_1", branches=(
                Branch(flow_id="Flow_3", probability=0.5),
                Branch(flow_id="Flow_4", probability=0.5),
            )),
        ),
    )


# --------------------------------------------------------------------------- #
# Patch sulla baseline
# --------------------------------------------------------------------------- #


def test_an_empty_patch_gives_back_the_baseline():
    assert apply_patch(_baseline(), ModelPatch()) == _baseline()


def test_a_patch_replaces_by_id_and_keeps_the_rest_in_order():
    approvers = ResourcePool(id="p", name="Ufficio", resources=(
        Resource(id="ops", name="Operatore", cost_per_hour=30, amount=3, calendar_id="office"),))
    slower_b = Activity(element_id="Task_B", assignments=(
        Assignment(resource_id="ops", duration=LogNormal(mean=900, variance=40000, minimum=60, maximum=5400)),))

    patched = apply_patch(_baseline(), ModelPatch(pools=(approvers,), activities=(slower_b,)))

    assert patched.resources()["ops"].amount == 3
    assert [a.element_id for a in patched.activities] == ["Task_A", "Task_B"]
    assert patched.activities[0] == _baseline().activities[0]
    assert isinstance(patched.activities[1].assignments[0].duration, LogNormal)


def test_a_patch_adds_what_the_baseline_did_not_have():
    night_shift = ResourcePool(id="night-pool", name="Turno di notte", resources=(
        Resource(id="night-ops", name="Operatore notte", cost_per_hour=40, amount=1, calendar_id="night"),))

    patched = apply_patch(_baseline(), ModelPatch(calendars=(NIGHT,), pools=(night_shift,)))

    assert [c.id for c in patched.calendars] == ["office", "night"]
    assert patched.resources()["night-ops"].calendar_id == "night"


def test_sections_without_ids_are_replaced_whole():
    size = CaseAttribute(name="importo", options=(
        DiscreteOption(value="1000", probability=0.7), DiscreteOption(value="9000", probability=0.3)))
    routed = Gateway(element_id="Gateway_1", branches=(
        Branch(flow_id="Flow_3", probability=0.5, condition=_when("importo", ">", 5000)),
        Branch(flow_id="Flow_4", probability=0.5, condition=_when("importo", "<=", 5000)),
    ))

    patched = apply_patch(_baseline(), ModelPatch(case_attributes=(size,), gateways=(routed,)))

    assert patched.case_attributes == (size,)
    assert patched.gateways[0].branches[0].condition is not None


def test_a_patch_that_breaks_a_reference_is_refused():
    orphan = Activity(element_id="Task_A", assignments=(
        Assignment(resource_id="nobody", duration=Normal(mean=600, std=60, minimum=420, maximum=780)),))

    with pytest.raises(ValidationError, match="risorsa sconosciuta nobody"):
        apply_patch(_baseline(), ModelPatch(activities=(orphan,)))


def test_a_patch_with_the_same_id_twice_is_refused():
    with pytest.raises(ValidationError, match="calendario nella patch duplicato: office"):
        ModelPatch(calendars=(OFFICE, OFFICE))
