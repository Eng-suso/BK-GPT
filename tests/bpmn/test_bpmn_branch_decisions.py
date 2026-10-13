"""Decisions on alternative paths, start triggers and outcome-labelled branches.

The reference is the public Camunda "invoice receipt" process: a rejected invoice
is reviewed, and a second decision sends it back to approval or rejects it.
"""

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


APPROVAL = ProcessDecision(
    id="approvata",
    label="Fattura approvata?",
    outcome_details=[
        ProcessDecisionOutcome(id="ok", label="Sì", condition="Approvata", target_ref="bonifico", is_default=True),
        ProcessDecisionOutcome(id="ko", label="No", condition="Respinta", target_path_id="revisione"),
    ],
)
REVIEW_OUTCOME = ProcessDecision(
    id="riuscita",
    label="Revisione riuscita?",
    outcome_details=[
        ProcessDecisionOutcome(id="chiarita", label="Sì", condition="Chiarita", target_ref="approva", is_default=True),
        ProcessDecisionOutcome(id="respinta", label="No", condition="Non chiaribile", target_path_id="rifiuto"),
    ],
)
APPROVAL_EDGE = ProcessFlowEdge(id="e1", source_id="approva", target_id="approvata", label="Esito")
EDGES = [APPROVAL_EDGE, ProcessFlowEdge(id="e2", source_id="rivedi", target_id="riuscita", label="Esito revisione")]


def _invoice(**overrides) -> ProcessUnderstanding:
    base = dict(
        title="Ricezione e pagamento fattura fornitore",
        actors=[
            ProcessActor(id="assistente", label="Assistente amministrativo", kind="role"),
            ProcessActor(id="approvatore", label="Approvatore", kind="role"),
            ProcessActor(id="contabilita", label="Contabilità", kind="team"),
        ],
        boundaries=ProcessBoundaries(
            trigger="Arriva la fattura del fornitore via PEC",
            start_event="Fattura ricevuta",
            success_end="Fattura pagata e archiviata",
            failure_ends=["Fattura respinta"],
        ),
        steps=[
            ProcessStep(id="assegna", label="Assegna l'approvatore", type="business_rule_task", actor_ids=["assistente"]),
            ProcessStep(id="approva", label="Approva la fattura", actor_ids=["approvatore"]),
            ProcessStep(id="rivedi", label="Rivedi la fattura", actor_ids=["assistente"]),
            ProcessStep(id="bonifico", label="Prepara il bonifico", actor_ids=["contabilita"]),
            ProcessStep(id="archivia", label="Archivia la fattura", type="service_task", actor_ids=["contabilita"]),
        ],
        main_success_path=["assegna", "approva", "bonifico", "archivia"],
        decisions=[APPROVAL, REVIEW_OUTCOME],
        alternative_paths=[
            ProcessPath(id="revisione", label="Revisione", trigger_or_condition="Respinta", sequence=["rivedi"]),
            ProcessPath(id="rifiuto", label="Fattura respinta", trigger_or_condition="Non chiaribile", sequence=[], ends_at="Fattura respinta"),
        ],
        flow_edges=EDGES,
    )
    base.update(overrides)
    return ProcessUnderstanding(**base)


def _compile(process: ProcessUnderstanding):
    return build_bpmn_semantic_model(process_id="Fattura", process_name=process.title, process=process)


def _node(model, name: str):
    return next(node for node in model.flowNodes if node.name == name)


def _past_merge(model, node_id: str) -> str:
    """The node a flow really reaches: an unnamed exclusive merge hands over to its single target."""
    node = next(n for n in model.flowNodes if n.id == node_id)
    out = [f for f in model.sequenceFlows if f.sourceRef == node_id]
    if node.type == "exclusiveGateway" and not node.name and len(out) == 1:
        return out[0].targetRef
    return node_id


def _flow(model, source: str, target: str):
    """The flow leaving `source` towards `target`, also through the merge in front of it."""
    source_id, target_id = _node(model, source).id, _node(model, target).id
    return next(
        f for f in model.sequenceFlows
        if f.sourceRef == source_id and target_id in (f.targetRef, _past_merge(model, f.targetRef))
    )


def test_a_decision_after_a_branch_step_becomes_a_gateway_on_that_branch():
    model = _compile(_invoice())

    review_gateway = _node(model, "Revisione riuscita?")
    assert review_gateway.type == "exclusiveGateway"
    assert _flow(model, "Rivedi la fattura", "Revisione riuscita?")
    assert _flow(model, "Revisione riuscita?", "Approva la fattura").name == "Sì"
    assert _flow(model, "Revisione riuscita?", "Fattura respinta").name == "No"
    assert not any("non mappabile" in warning for warning in model.model_warnings)


def test_a_reviewed_invoice_never_ends_as_paid():
    model = _compile(_invoice())

    review = _node(model, "Rivedi la fattura")
    paid = _node(model, "Fattura pagata e archiviata")
    assert not any(f.sourceRef == review.id and f.targetRef == paid.id for f in model.sequenceFlows)
    structural = [issue for issue in validate_bpmn_semantic_model(model) if not issue.startswith("Soundness:")]
    assert structural == []
    assert not analyze_control_flow(model).errors


def test_a_decision_with_no_anchor_anywhere_is_still_reported():
    process = _invoice(flow_edges=[APPROVAL_EDGE])

    model = _compile(process)

    assert any("Revisione riuscita?" in warning and "non mappabile" in warning for warning in model.model_warnings)


def test_a_path_with_neither_rejoin_nor_end_is_flagged_instead_of_closing_silently():
    process = _invoice(
        decisions=[APPROVAL],
        alternative_paths=[ProcessPath(id="revisione", label="Revisione", trigger_or_condition="Respinta", sequence=["rivedi"])],
        flow_edges=[APPROVAL_EDGE],
    )

    model = _compile(process)

    assert any("senza rientro ne' fine esplicita" in warning for warning in model.model_warnings)


def test_outcomes_label_their_branches_and_only_non_default_ones_carry_a_condition():
    model = _compile(_invoice())

    approved = _node(model, "Fattura approvata?")
    to_payment = _flow(model, "Fattura approvata?", "Prepara il bonifico")
    to_review = _flow(model, "Fattura approvata?", "Rivedi la fattura")
    assert (to_payment.name, to_payment.conditionExpression) == ("Sì", None)
    assert (to_review.name, to_review.conditionExpression) == ("No", "Respinta")
    assert approved.defaultFlowId == to_payment.id


def test_a_declared_default_stays_the_default_even_if_a_flow_edge_gives_it_a_condition():
    edges = [
        *EDGES,
        ProcessFlowEdge(id="e3", source_id="riuscita", target_id="approva", label="Sì", condition="Chiarita"),
    ]
    model = _compile(_invoice(flow_edges=edges))

    back_to_approval = _flow(model, "Revisione riuscita?", "Approva la fattura")
    assert back_to_approval.conditionExpression is None
    assert _node(model, "Revisione riuscita?").defaultFlowId == back_to_approval.id


def test_the_start_event_carries_the_trigger_the_plan_declares():
    message = _compile(_invoice())
    timer = _compile(_invoice(boundaries=ProcessBoundaries(trigger="Ogni fine mese", start_event="Chiusura mensile")))
    plain = _compile(_invoice(boundaries=ProcessBoundaries(start_event="Inizio")))

    assert _node(message, "Fattura ricevuta").eventDefinition == "message"
    assert "<bpmn:messageEventDefinition" in semantic_model_to_bpmn_xml(message)
    assert _node(timer, "Chiusura mensile").eventDefinition == "timer"
    assert _node(plain, "Inizio").eventDefinition is None


def test_task_types_follow_the_plan():
    model = _compile(_invoice())

    assert _node(model, "Assegna l'approvatore").type == "businessRuleTask"
    assert _node(model, "Approva la fattura").type == "userTask"
    assert _node(model, "Archivia la fattura").type == "serviceTask"
