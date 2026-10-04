"""Simulation IR: validazione, compilazione verso Prosimos, ponte dalla richiesta."""

import pytest
from pydantic import ValidationError

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    SimGatewayBranchConfig,
    SimGatewayConfig,
    SimResourceConfig,
    SimTaskConfig,
)
from backend.simulation.ir import compile_for_prosimos, model_from_request
from backend.simulation.ir.model import (
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
    Fixed,
    Gamma,
    Gateway,
    LogNormal,
    Normal,
    PriorityRule,
    Provenance,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
    SourceRef,
    Uniform,
)
from backend.simulation.scenario_builder import build_prosimos_scenario, parse_bpmn_for_simulation

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN = (
    f'<definitions xmlns="{NS}"><process id="P">'
    '<startEvent id="S"/><task id="T_receive" name="Ricevi"/>'
    '<exclusiveGateway id="G" name="Importo"/>'
    '<task id="T_approve" name="Approva"/><exclusiveGateway id="J"/>'
    '<task id="T_pay" name="Paga"/><endEvent id="E"/>'
    '<sequenceFlow id="F0" sourceRef="S" targetRef="T_receive"/>'
    '<sequenceFlow id="F1" sourceRef="T_receive" targetRef="G"/>'
    '<sequenceFlow id="F_high" sourceRef="G" targetRef="T_approve"/>'
    '<sequenceFlow id="F_low" sourceRef="G" targetRef="J"/>'
    '<sequenceFlow id="F2" sourceRef="T_approve" targetRef="J"/>'
    '<sequenceFlow id="F3" sourceRef="J" targetRef="T_pay"/>'
    '<sequenceFlow id="F4" sourceRef="T_pay" targetRef="E"/>'
    "</process></definitions>"
)


# --------------------------------------------------------------------------- #
# Ponte dalla richiesta: stesso scenario del builder storico
# --------------------------------------------------------------------------- #

REQUESTS = {
    "default": CreateSimulationRunRequest(),
    "globali": CreateSimulationRunRequest(
        arrival_interval_seconds=600, default_task_duration_seconds=1200,
        default_cost_per_hour=48.5, resource_amount=3, resource_name="  Buyer  ",
    ),
    "override_attivita_e_gateway": CreateSimulationRunRequest(
        tasks=[
            SimTaskConfig(element_id="T_receive", mean_seconds=300, distribution="fixed"),
            SimTaskConfig(element_id="T_approve", mean_seconds=0.5, distribution="expon"),
            SimTaskConfig(element_id="T_pay", mean_seconds=900),
        ],
        gateways=[SimGatewayConfig(element_id="G", branches=[
            SimGatewayBranchConfig(flow_id="F_high", probability=0.2),
            SimGatewayBranchConfig(flow_id="F_low", probability=0.6),
        ])],
    ),
    "gateway_a_zero": CreateSimulationRunRequest(
        gateways=[SimGatewayConfig(element_id="G", branches=[
            SimGatewayBranchConfig(flow_id="F_high", probability=0),
            SimGatewayBranchConfig(flow_id="F_low", probability=0),
        ])],
    ),
    "risorse_esplicite": CreateSimulationRunRequest(
        resources=[
            SimResourceConfig(id="ops", name="Operatori", cost_per_hour=30, amount=2),
            SimResourceConfig(id="appr", name="Approvatori", cost_per_hour=60, amount=1),
        ],
        tasks=[
            SimTaskConfig(element_id="T_receive", mean_seconds=600, resource_id="ops"),
            SimTaskConfig(element_id="T_approve", mean_seconds=1800, resource_id="appr"),
            SimTaskConfig(element_id="T_pay", mean_seconds=900, resource_id="ops", distribution="expon"),
        ],
    ),
}


@pytest.mark.parametrize("name", REQUESTS)
def test_the_ir_compiles_to_the_scenario_the_builder_produced(name):
    request = REQUESTS[name]
    tasks, gateways = parse_bpmn_for_simulation(BPMN)

    compiled = compile_for_prosimos(model_from_request(request, tasks, gateways))

    assert compiled == build_prosimos_scenario(bpmn_xml=BPMN, request=request).payload


@pytest.mark.parametrize(
    "request_, message",
    [
        (CreateSimulationRunRequest(resources=[]), "almeno una risorsa"),
        (
            CreateSimulationRunRequest(resources=[
                SimResourceConfig(id="a", name="A", cost_per_hour=1, amount=1),
                SimResourceConfig(id="a", name="B", cost_per_hour=1, amount=1),
            ]),
            "distinti",
        ),
        (
            CreateSimulationRunRequest(resources=[SimResourceConfig(id="a", name="A", cost_per_hour=1, amount=1)]),
            "risorsa valida",
        ),
    ],
)
def test_the_bridge_keeps_the_builder_messages(request_, message):
    tasks, gateways = parse_bpmn_for_simulation(BPMN)

    with pytest.raises(ValueError, match=message):
        model_from_request(request_, tasks, gateways)


def test_the_bridge_marks_what_the_consultant_entered_and_what_is_assumed():
    tasks, gateways = parse_bpmn_for_simulation(BPMN)
    request = CreateSimulationRunRequest(tasks=[SimTaskConfig(element_id="T_pay", mean_seconds=900)])

    model = model_from_request(request, tasks, gateways)

    by_id = {a.element_id: a.assignments[0].provenance for a in model.activities}
    assert by_id["T_pay"] == Provenance(origin="manual")
    # Una durata di default non l'ha detta nessuno: nessuna provenienza.
    assert by_id["T_receive"] is None
    assert all(b.provenance is None for b in model.gateways[0].branches)


# --------------------------------------------------------------------------- #
# Validazione semantica del modello
# --------------------------------------------------------------------------- #

OFFICE = Calendar(id="office", name="Ufficio", periods=(
    CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),
))


def _model(**overrides) -> SimulationModel:
    base = dict(
        arrival=Arrival(interarrival=Exponential(mean=1800, minimum=0, maximum=18000), calendar_id="office"),
        calendars=(OFFICE,),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=2, calendar_id="office"),
        )),),
        activities=(Activity(element_id="T_pay", assignments=(
            Assignment(resource_id="ops", duration=Fixed(value=600)),
        )),),
    )
    base.update(overrides)
    return SimulationModel(**base)


@pytest.mark.parametrize(
    "make, message",
    [
        (lambda: Normal(mean=10, std=1, minimum=20, maximum=5), "minimo"),
        (lambda: Normal(mean=50, std=1, minimum=0, maximum=20), "media"),
        (lambda: Exponential(mean=100, minimum=100, maximum=500), "media"),
        (lambda: Uniform(minimum=5, maximum=5), "minimo"),
        (lambda: CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="22:00:00", end="06:00:00"), "mezzanotte"),
        (lambda: CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="9:00", end="17:00:00"), "orario"),
        (lambda: Gateway(element_id="G", branches=(
            Branch(flow_id="a", probability=0.5), Branch(flow_id="b", probability=0.4))), "sommano"),
        (lambda: Gateway(element_id="G", branches=(
            Branch(flow_id="a", probability=0.5,
                   condition=Condition(any_of=((Rule(attribute="x", operator=">", value=1),),))),
            Branch(flow_id="b", probability=0.5))), "tutti i rami"),
        (lambda: CaseAttribute(name="tipo", options=(DiscreteOption(value="a", probability=0.5),)), "sommano"),
        (lambda: CaseAttribute(name="tipo"), "opzioni discrete o una distribuzione"),
    ],
)
def test_a_parameter_that_cannot_be_simulated_is_refused_with_the_reason(make, message):
    with pytest.raises(ValidationError, match=message):
        make()


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"arrival": Arrival(interarrival=Fixed(value=60), calendar_id="night")}, "calendario degli arrivi"),
        ({"activities": (Activity(element_id="T", assignments=(
            Assignment(resource_id="ghost", duration=Fixed(value=1)),)),)}, "risorsa sconosciuta"),
        ({"calendars": (OFFICE, OFFICE)}, "calendario duplicato"),
        ({"priority_rules": (PriorityRule(level=1, condition=Condition(any_of=(
            (Rule(attribute="tipo", operator="=", value="premium"),),))),)}, "attributi che il caso non ha"),
    ],
)
def test_references_inside_the_model_must_exist(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _model(**overrides)


def test_the_model_is_immutable_and_rejects_unknown_fields():
    model = _model()
    with pytest.raises(ValidationError):
        model.activities = ()
    with pytest.raises(ValidationError):
        Fixed(value=1, mean=2)


# --------------------------------------------------------------------------- #
# Compilazione delle capacita' 2.x
# --------------------------------------------------------------------------- #


def _rich_model() -> SimulationModel:
    approvals = Calendar(id="appr", name="Approvazioni", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="THURSDAY", begin="10:00:00", end="14:00:00"),
    ))
    high = Condition(any_of=((Rule(attribute="importo", operator=">", value=5000),),))
    low = Condition(any_of=((Rule(attribute="importo", operator="<=", value=5000),),))
    return _model(
        calendars=(OFFICE, approvals),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=2, calendar_id="office"),
            Resource(id="appr", name="Approvatore", cost_per_hour=60, amount=1, calendar_id="appr",
                     provenance=Provenance(origin="declared", confidence="medium",
                                           sources=(SourceRef(kind="claim", id="c-1"),))),
        )),),
        activities=(
            Activity(element_id="T_receive", assignments=(
                Assignment(resource_id="ops", duration=LogNormal(mean=600, variance=3600, minimum=60, maximum=3600)),
            )),
            Activity(element_id="T_approve", assignments=(
                Assignment(resource_id="appr", duration=Gamma(mean=1800, variance=90000, minimum=300, maximum=7200)),
                Assignment(resource_id="ops", duration=Uniform(minimum=1800, maximum=3600)),
            )),
        ),
        gateways=(Gateway(element_id="G", branches=(
            Branch(flow_id="F_high", probability=0.5, condition=high),
            Branch(flow_id="F_low", probability=0.5, condition=low),
        )),),
        case_attributes=(
            CaseAttribute(name="tipo", options=(DiscreteOption(value="premium", probability=0.2),
                                                DiscreteOption(value="standard", probability=0.8))),
            CaseAttribute(name="importo", distribution=Uniform(minimum=100, maximum=12000)),
        ),
        attribute_updates=(AttributeUpdate(element_id="T_receive", name="rischio", expression="importo / 1000"),),
        priority_rules=(
            PriorityRule(level=2, condition=Condition(any_of=((Rule(attribute="tipo", operator="=", value="standard"),),))),
            PriorityRule(level=1, condition=Condition(any_of=((Rule(attribute="tipo", operator="=", value="premium"),),))),
        ),
    )


def test_conditional_routing_compiles_to_branch_rules_linked_to_each_path():
    payload = compile_for_prosimos(_rich_model())

    probabilities = payload["gateway_branching_probabilities"][0]["probabilities"]
    assert [p["condition_id"] for p in probabilities] == ["G::F_high", "G::F_low"]
    assert payload["branch_rules"][0] == {
        "id": "G::F_high",
        "rules": [[{"attribute": "importo", "comparison": ">", "value": "5000"}]],
    }


def test_each_resource_gets_its_own_calendar_and_only_used_calendars_are_sent():
    payload = compile_for_prosimos(_rich_model())

    resources = {r["id"]: r for r in payload["resource_profiles"][0]["resource_list"]}
    assert resources["appr"]["calendar"] == "appr"
    assert [c["id"] for c in payload["resource_calendars"]] == ["office", "appr"]
    assert payload["arrival_time_calendar"] == [
        {"from": "MONDAY", "to": "FRIDAY", "beginTime": "09:00:00", "endTime": "17:00:00"}
    ]


def test_an_activity_can_be_done_by_more_resources_with_their_own_durations():
    payload = compile_for_prosimos(_rich_model())

    approve = next(t for t in payload["task_resource_distribution"] if t["task_id"] == "T_approve")
    assert [(r["resource_id"], r["distribution_name"]) for r in approve["resources"]] == [
        ("appr", "gamma"), ("ops", "uniform")
    ]
    resources = {r["id"]: r for r in payload["resource_profiles"][0]["resource_list"]}
    assert resources["ops"]["assignedTasks"] == ["T_receive", "T_approve"]


def test_attributes_updates_and_priorities_compile_to_the_engine_sections():
    payload = compile_for_prosimos(_rich_model())

    assert payload["case_attributes"][0] == {
        "name": "tipo", "type": "discrete",
        "values": [{"key": "premium", "value": 0.2}, {"key": "standard", "value": 0.8}],
    }
    assert payload["case_attributes"][1]["values"]["distribution_name"] == "uniform"
    assert payload["event_attributes"] == [{"event_id": "T_receive", "attributes": [
        {"name": "rischio", "type": "expression", "values": "importo / 1000"}]}]
    assert [r["priority_level"] for r in payload["prioritisation_rules"]] == [1, 2]


def test_a_model_without_2x_features_stays_runnable_on_the_old_engine():
    payload = compile_for_prosimos(_model())

    assert not {"branch_rules", "event_attributes", "prioritisation_rules"} & payload.keys()


@pytest.mark.parametrize(
    "distribution, name, values",
    [
        (Fixed(value=60), "fix", [60.0]),
        (Exponential(mean=60, minimum=0, maximum=600), "expon", [60.0, 0.0, 600.0]),
        (Uniform(minimum=10, maximum=20), "uniform", [10.0, 20.0]),
        (Normal(mean=60, std=6, minimum=42, maximum=78), "norm", [60.0, 6.0, 42.0, 78.0]),
        (LogNormal(mean=60, variance=100, minimum=1, maximum=600), "lognorm", [60.0, 100.0, 1.0, 600.0]),
        (Gamma(mean=60, variance=100, minimum=1, maximum=600), "gamma", [60.0, 100.0, 1.0, 600.0]),
    ],
)
def test_every_distribution_uses_the_parameter_order_of_the_engine(distribution, name, values):
    from backend.simulation.ir.compile import distribution_params

    compiled = distribution_params(distribution)

    assert compiled["distribution_name"] == name
    assert [p["value"] for p in compiled["distribution_params"]] == values
