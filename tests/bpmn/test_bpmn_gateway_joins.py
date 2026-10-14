"""Every BPMN 2.0 gateway the plan can ask for, with the join its branches need.

OMG BPMN 2.0, 10.5: exclusive (XOR), inclusive (OR), parallel (AND), complex
and event-based gateways; an event-based gateway may also start the process.
"""

import pytest

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.bpmn.soundness import analyze_control_flow
from backend.bpmn.validation import validate_bpmn_semantic_model
from backend.process_understanding import (
    ProcessActor,
    ProcessBoundaries,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _order(gateway_type: str, **decision) -> ProcessUnderstanding:
    """Receive an order, then prepare the goods and invoice the customer, then ship."""
    return ProcessUnderstanding(
        title="Evasione ordine",
        actors=[ProcessActor(id="magazzino", label="Magazzino", kind="team")],
        boundaries=ProcessBoundaries(start_event="Ordine ricevuto", success_end="Ordine spedito"),
        steps=[
            ProcessStep(id="ricevi", label="Registra l'ordine", actor_ids=["magazzino"]),
            ProcessStep(id="prepara", label="Prepara la merce", actor_ids=["magazzino"]),
            ProcessStep(id="fattura", label="Emetti la fattura", type="service_task", actor_ids=["magazzino"]),
            ProcessStep(id="spedisci", label="Spedisci", actor_ids=["magazzino"]),
        ],
        main_success_path=["ricevi", "prepara", "spedisci"],
        decisions=[
            ProcessDecision(
                id="split",
                label="Preparazione e fatturazione",
                gateway_type=gateway_type,
                outcome_details=[
                    ProcessDecisionOutcome(id="merce", label="Merce", condition="Merce a magazzino", target_ref="prepara", is_default=True),
                    ProcessDecisionOutcome(id="conto", label="Fattura", condition="Cliente a credito", target_path_id="fatturazione"),
                ],
                **decision,
            )
        ],
        alternative_paths=[
            ProcessPath(id="fatturazione", label="Fatturazione", sequence=["fattura"], rejoins_at="spedisci"),
        ],
        flow_edges=[ProcessFlowEdge(id="e1", source_id="ricevi", target_id="split", label="Ordine registrato")],
    )


def _compile(process: ProcessUnderstanding):
    return build_bpmn_semantic_model(process_id="Ordine", process_name=process.title, process=process)


def _node(model, name: str):
    return next(node for node in model.flowNodes if node.name == name)


def _into(model, node_id: str):
    return [flow for flow in model.sequenceFlows if flow.targetRef == node_id]


def _out_of(model, node_id: str):
    return [flow for flow in model.sequenceFlows if flow.sourceRef == node_id]


def _sound(model) -> None:
    structural = [issue for issue in validate_bpmn_semantic_model(model) if not issue.startswith("Soundness:")]
    assert structural == []
    assert not analyze_control_flow(model).errors


@pytest.mark.parametrize(
    ("gateway_type", "bpmn_type"),
    [("parallel", "parallelGateway"), ("inclusive", "inclusiveGateway"), ("complex", "complexGateway")],
)
def test_branches_that_run_together_meet_in_a_join_of_the_same_type(gateway_type, bpmn_type):
    model = _compile(_order(gateway_type))

    split = _node(model, "Preparazione e fatturazione")
    ship = _node(model, "Spedisci")
    (into_ship,) = _into(model, ship.id)
    join = next(node for node in model.flowNodes if node.id == into_ship.sourceRef)
    assert split.type == join.type == bpmn_type
    assert {flow.sourceRef for flow in _into(model, join.id)} == {
        _node(model, "Prepara la merce").id,
        _node(model, "Emetti la fattura").id,
    }
    _sound(model)
    assert not analyze_control_flow(model).warnings


def test_parallel_branches_carry_their_label_but_never_a_condition_or_default():
    model = _compile(_order("parallel"))

    split = _node(model, "Preparazione e fatturazione")
    branches = _out_of(model, split.id)
    assert sorted(flow.name for flow in branches) == ["Fattura", "Merce"]
    assert all(flow.conditionExpression is None for flow in branches)
    assert split.defaultFlowId is None


def test_a_complex_gateway_carries_its_activation_rule_and_a_default():
    model = _compile(_order("complex", activation_condition="almeno un ramo completato"))

    split = _node(model, "Preparazione e fatturazione")
    xml = semantic_model_to_bpmn_xml(model, include_di=False)
    assert split.activationCondition == "almeno un ramo completato"
    assert split.defaultFlowId == _flow_named(model, split.id, "Merce").id
    assert '<bpmn:complexGateway id="split"' in xml
    assert "<bpmn:activationCondition" in xml
    assert f'default="{split.defaultFlowId}"' in xml


def test_an_exclusive_split_merges_without_a_join():
    model = _compile(_order("exclusive"))

    ship = _node(model, "Spedisci")
    assert {flow.sourceRef for flow in _into(model, ship.id)} == {
        _node(model, "Prepara la merce").id,
        _node(model, "Emetti la fattura").id,
    }
    # Alternative branches converge on the activity: correct BPMN, nothing to warn about.
    assert not [issue for issue in analyze_control_flow(model).warnings if issue.code == "uncontrolled_merge"]


def test_parallel_branches_entering_an_activity_without_their_join_are_flagged():
    model = _compile(_order("parallel"))
    join = next(n for n in model.flowNodes if n.type == "parallelGateway" and len(_into(model, n.id)) > 1)
    [exit_flow] = [f for f in model.sequenceFlows if f.sourceRef == join.id]
    for flow in _into(model, join.id):
        flow.targetRef = exit_flow.targetRef
    model.sequenceFlows.remove(exit_flow)
    model.flowNodes.remove(join)

    merges = [i for i in analyze_control_flow(model).warnings if i.code == "uncontrolled_merge"]
    assert [issue.node_id for issue in merges] == [_node(model, "Spedisci").id]


def test_an_event_based_gateway_can_start_the_process_and_wait_for_every_event():
    process = ProcessUnderstanding(
        title="Avvio pratica",
        actors=[ProcessActor(id="ufficio", label="Ufficio", kind="team")],
        boundaries=ProcessBoundaries(success_end="Pratica aperta"),
        steps=[
            ProcessStep(id="apri", label="Apri la pratica", actor_ids=["ufficio"]),
            ProcessStep(id="chiama", label="Richiama il cliente", actor_ids=["ufficio"]),
        ],
        main_success_path=["apri"],
        decisions=[
            ProcessDecision(
                id="arrivo",
                label="Come arriva la richiesta?",
                gateway_type="event_based",
                instantiate=True,
                event_gateway_type="parallel",
                outcome_details=[
                    ProcessDecisionOutcome(id="mail", label="Email ricevuta", target_ref="apri"),
                    ProcessDecisionOutcome(id="tel", label="Telefonata ricevuta", target_path_id="telefono"),
                ],
            )
        ],
        alternative_paths=[ProcessPath(id="telefono", label="Telefono", sequence=["chiama"], ends_at="Pratica aperta")],
        flow_edges=[
            ProcessFlowEdge(id="e1", source_id="arrivo", target_id="apri", label="Email ricevuta"),
            ProcessFlowEdge(id="e2", source_id="arrivo", target_id="chiama", label="Telefonata ricevuta"),
        ],
    )

    model = _compile(process)

    gateway = _node(model, "Come arriva la richiesta?")
    assert (gateway.type, gateway.instantiate, gateway.eventGatewayType) == ("eventBasedGateway", True, "Parallel")
    assert not any(node.type == "startEvent" for node in model.flowNodes)
    assert _into(model, gateway.id) == []
    assert {model_node.type for model_node in model.flowNodes if model_node.id in {f.targetRef for f in _out_of(model, gateway.id)}} == {
        "intermediateCatchEvent"
    }
    assert 'instantiate="true" eventGatewayType="Parallel"' in semantic_model_to_bpmn_xml(model, include_di=False)
    _sound(model)


def test_soundness_rejects_a_condition_on_a_parallel_branch():
    model = _compile(_order("parallel"))
    split = _node(model, "Preparazione e fatturazione")
    _out_of(model, split.id)[0].conditionExpression = "importo > 100"

    codes = {issue.code for issue in analyze_control_flow(model).errors}

    assert "parallel_gateway_condition" in codes


def test_every_gateway_is_laid_out():
    for gateway_type in ("parallel", "inclusive", "complex", "exclusive"):
        assert "<bpmndi:BPMNDiagram" in semantic_model_to_bpmn_xml(_compile(_order(gateway_type)))


def _flow_named(model, source_id: str, name: str):
    return next(flow for flow in _out_of(model, source_id) if flow.name == name)
