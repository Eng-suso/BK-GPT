"""L'IR compilato gira davvero su Prosimos 2.x, e le capacita' hanno effetto.

Serve Prosimos nell'interprete (Python 3.11-3.12): nella CI del backend si
salta e lo esegue il job ``prosimos-runner``. In locale, nell'ambiente del
runner (``ops/prosimos/runner/requirements-test.txt``) e senza ``.env``:

    pytest --noconftest tests/simulation/test_simulation_ir_engine.py
"""

import json
import random
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("prosimos")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "spike"))

import contract_spike  # noqa: E402

from backend.simulation.ir import compile_for_prosimos  # noqa: E402
from backend.simulation.ir.model import (  # noqa: E402
    Activity,
    Arrival,
    Assignment,
    AttributeUpdate,
    Branch,
    Calendar,
    CalendarPeriod,
    CaseAttribute,
    Condition,
    DiscreteOption,
    Exponential,
    Gateway,
    Normal,
    PriorityRule,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
    Uniform,
)


def _when(attribute, operator, value) -> Condition:
    return Condition(any_of=((Rule(attribute=attribute, operator=operator, value=value),),))


def _model(*, busy: bool = False) -> SimulationModel:
    office = Calendar(id="office", name="Ufficio", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),))
    approvals = Calendar(id="appr", name="Approvazioni", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="THURSDAY", begin="10:00:00", end="14:00:00"),))
    return SimulationModel(
        arrival=Arrival(
            interarrival=Exponential(mean=400 if busy else 1800, minimum=0, maximum=18000),
            calendar_id="office",
        ),
        calendars=(office, approvals),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=1 if busy else 2, calendar_id="office"),
            Resource(id="appr", name="Approvatore", cost_per_hour=60, amount=1, calendar_id="appr"),
        )),),
        activities=(
            Activity(element_id="T_receive", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=600, std=120, minimum=120, maximum=1200)),)),
            Activity(element_id="T_approve", assignments=(
                Assignment(resource_id="appr", duration=Uniform(minimum=600, maximum=2400)),)),
            Activity(element_id="T_pay", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=900, std=180, minimum=300, maximum=1800)),)),
        ),
        gateways=(Gateway(element_id="G_split", branches=(
            Branch(flow_id="F_high", probability=0.5, condition=_when("importo", ">", 5000)),
            Branch(flow_id="F_low", probability=0.5, condition=_when("importo", "<=", 5000)),
        )),),
        case_attributes=(
            CaseAttribute(name="tipo", options=(DiscreteOption(value="premium", probability=0.2),
                                                DiscreteOption(value="standard", probability=0.8))),
            CaseAttribute(name="importo", distribution=Uniform(minimum=100, maximum=12000)),
        ),
        attribute_updates=(AttributeUpdate(element_id="T_receive", name="rischio", expression="importo / 1000"),),
        priority_rules=(
            PriorityRule(level=1, condition=_when("tipo", "=", "premium")),
            PriorityRule(level=2, condition=_when("tipo", "=", "standard")),
        ),
    )


def _run(model: SimulationModel, seed: int = 5) -> list[dict]:
    import numpy
    from prosimos.simulation_engine import run_simulation

    random.seed(seed)
    numpy.random.seed(seed)
    with tempfile.TemporaryDirectory() as tmp:
        scenario, log = Path(tmp) / "s.json", Path(tmp) / "log.csv"
        scenario.write_text(json.dumps(compile_for_prosimos(model)))
        run_simulation(str(contract_spike.BPMN_PATH), str(scenario), 200, None, str(log), contract_spike.START)
        return contract_spike.parse_log(log.read_text())


def test_conditional_routing_from_the_ir_is_applied():
    assert contract_spike.check_branch_rules(_run(_model())) is None


def test_attribute_updates_from_the_ir_reach_the_log():
    assert contract_spike.check_event_attributes(_run(_model())) is None


def test_resource_calendars_from_the_ir_are_respected():
    assert contract_spike.check_calendars(_run(_model())) is None


def test_priority_rules_from_the_ir_serve_premium_first():
    assert contract_spike.check_prioritisation(_run(_model(busy=True))) is None
