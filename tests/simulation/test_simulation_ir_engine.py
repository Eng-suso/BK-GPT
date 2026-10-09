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
    LogNormal,
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


def _run(model: SimulationModel, seed: int = 5, *, payload: dict | None = None) -> list[dict]:
    import numpy
    from prosimos.simulation_engine import run_simulation

    random.seed(seed)
    numpy.random.seed(seed)
    with tempfile.TemporaryDirectory() as tmp:
        scenario, log = Path(tmp) / "s.json", Path(tmp) / "log.csv"
        scenario.write_text(json.dumps(payload if payload is not None else compile_for_prosimos(model)))
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


def test_a_run_from_the_v2_contract_keeps_calendars_lognormal_and_rules_on_the_engine():
    # SIM-37, criterio d'uscita: lo scenario esce dal builder della richiesta v2
    # (verifica sul BPMN compresa), non da `compile_for_prosimos` chiamato a mano.
    from backend.simulation.scenario_builder import build_prosimos_scenario_from_model

    base = _model()
    approve = Activity(element_id="T_approve", assignments=(
        Assignment(resource_id="appr", duration=LogNormal(mean=1500, variance=250000, minimum=300, maximum=6000)),))
    model = base.model_copy(update={"activities": (base.activities[0], approve, base.activities[2])})
    scenario = build_prosimos_scenario_from_model(
        bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), model=model)

    durations = {t["task_id"]: t["resources"][0]["distribution_name"] for t in scenario.payload["task_resource_distribution"]}
    assert durations["T_approve"] == "lognorm"
    rows = _run(model, payload=scenario.payload)
    assert contract_spike.check_branch_rules(rows) is None
    assert contract_spike.check_calendars(rows) is None


def test_a_task_with_other_resources_is_shared_on_the_engine():
    # A2-2: l'approvazione la fanno l'approvatore e, quando lui e' occupato o fuori
    # orario, un senior con la sua durata. Sul motore lavorano entrambi.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        arrival_interval_seconds=400,
        resources=[
            {"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 2},
            {"id": "appr", "name": "Approvatore", "cost_per_hour": 60, "amount": 1},
            {"id": "senior", "name": "Senior", "cost_per_hour": 90, "amount": 1},
        ],
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "ops"},
            {"element_id": "T_approve", "mean_seconds": 1800, "resource_id": "appr",
             "other_assignments": [{"resource_id": "senior", "mean_seconds": 900, "distribution": "fixed"}]},
            {"element_id": "T_pay", "mean_seconds": 600, "resource_id": "ops"},
        ],
    )
    scenario = build_prosimos_scenario(bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), request=request)

    rows = [row for row in _run(_model(), payload=scenario.payload) if row["activity"] == "Approva"]
    by_resource: dict[str, list[float]] = {}
    for row in rows:
        by_resource.setdefault(row["resource"].rsplit("_", 1)[0], []).append(row["end"] - row["start"])
    assert set(by_resource) == {"Approvatore", "Senior"}, by_resource.keys()
    # Ognuno con la sua durata: il senior e' fisso a 15 minuti di lavoro. Un'approvazione
    # iniziata a fine turno riprende il mattino dopo (calendario standard, 16 ore di
    # pausa notturna), quindi il tempo trascorso e' 15 minuti piu' le notti di mezzo.
    night = 16 * 3600
    assert all(round(seconds - 900) % night == 0 for seconds in by_resource["Senior"]), by_resource["Senior"]
    assert min(by_resource["Senior"]) == 900


def _amount_rule(operator: str) -> dict:
    return {"any_of": [[{"attribute": "importo", "operator": operator, "value": 5000}]]}


def test_a_v1_run_with_a_model_patch_routes_by_the_consultant_rules():
    # A2-1: il pannello manda la richiesta v1 e, in `model_patch`, attributi e
    # rami per regola; sul motore i casi sopra soglia passano dall'approvazione.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        model_patch={
            "case_attributes": [{"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}}],
            "gateways": [{"element_id": "G_split", "branches": [
                {"flow_id": "F_high", "probability": 0.5, "condition": _amount_rule(">")},
                {"flow_id": "F_low", "probability": 0.5, "condition": _amount_rule("<=")},
            ]}],
        },
    )
    scenario = build_prosimos_scenario(bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), request=request)

    assert contract_spike.check_branch_rules(_run(_model(), payload=scenario.payload)) is None
