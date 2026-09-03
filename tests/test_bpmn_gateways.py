"""Gateway coverage: exclusive (default), inclusive and event-based decisions."""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.bpmn.models import BPMNFlowNode, BPMNSemanticModel, BPMNSequenceFlow
from backend.bpmn.soundness import analyze_control_flow
from backend.process_understanding import (
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _process(gateway_type: str, *, outcome_label: str = "Serve una correzione") -> ProcessUnderstanding:
    """
    Build an order-review process model with the specified gateway type and correction outcome.
    
    Parameters:
        gateway_type (str): Gateway type used for the review decision.
        outcome_label (str): Label for the correction outcome and alternative path.
    
    Returns:
        ProcessUnderstanding: The configured order-review process model.
    """
    return ProcessUnderstanding(
        title="Order Review",
        steps=[
            ProcessStep(id="Task_Receive", label="Ricevi ordine"),
            ProcessStep(id="Task_Review", label="Rivedi ordine"),
            ProcessStep(id="Task_Correct", label="Correggi ordine"),
            ProcessStep(id="Task_Ship", label="Spedisci ordine"),
        ],
        sequence=["Task_Receive", "Task_Review", "Task_Ship"],
        main_success_path=["Task_Receive", "Task_Review", "Task_Ship"],
        decisions=[
            ProcessDecision(
                id="Decision_Review",
                label="Esito revisione",
                gateway_type=gateway_type,
                outcomes=["Ordine ok", outcome_label],
                outcome_details=[
                    ProcessDecisionOutcome(id="O_Ok", label="Ordine ok", target_ref="Task_Ship"),
                    ProcessDecisionOutcome(id="O_Fix", label=outcome_label, target_path_id="Alt_Fix"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="Alt_Fix",
                label="Correzione",
                trigger_or_condition=outcome_label,
                sequence=["Task_Correct"],
                rejoins_at="Task_Review",
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="Task_Receive", target_id="Task_Review", label="ricevuto"),
            ProcessFlowEdge(id="E2", source_id="Task_Review", target_id="Decision_Review", label="rivisto"),
            ProcessFlowEdge(
                id="E3", source_id="Decision_Review", target_id="Task_Ship",
                label="Ordine ok", condition="Ordine ok",
            ),
            ProcessFlowEdge(
                id="E4", source_id="Decision_Review", target_id="Task_Correct",
                label=outcome_label, condition=outcome_label, path_id="Alt_Fix",
            ),
        ],
        unknowns=[],
    )


def _compile(process: ProcessUnderstanding) -> BPMNSemanticModel:
    """Compile the order review process into a BPMN semantic model.
    
    Parameters:
    	process (ProcessUnderstanding): Process understanding to compile.
    
    Returns:
    	BPMNSemanticModel: BPMN semantic model for the order review process.
    """
    return build_bpmn_semantic_model(
        process_id="Process_Order", process_name="Order Review", process=process
    )


def test_decision_without_a_gateway_type_still_compiles_to_an_exclusive_gateway():
    model = _compile(_process("exclusive"))
    gateways = [node for node in model.flowNodes if node.type.endswith("Gateway")]
    assert [g.type for g in gateways] == ["exclusiveGateway"]


def test_inclusive_decision_compiles_to_an_inclusive_gateway():
    model = _compile(_process("inclusive"))
    gateway = next(node for node in model.flowNodes if node.type.endswith("Gateway"))
    assert gateway.type == "inclusiveGateway"
    outgoing = [flow for flow in model.sequenceFlows if flow.sourceRef == gateway.id]
    assert len(outgoing) >= 2
    # a bare branch on a data-based gateway is marked as the default
    assert any(flow.conditionExpression for flow in outgoing)
    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:inclusiveGateway" in xml
    assert analyze_control_flow(model).is_sound


def test_event_based_decision_forks_onto_catch_events():
    model = _compile(_process("event_based", outcome_label="Nessuna risposta dopo 5 giorni"))
    gateway = next(node for node in model.flowNodes if node.type.endswith("Gateway"))
    assert gateway.type == "eventBasedGateway"

    node_by_id = {node.id: node for node in model.flowNodes}
    branch_targets = [
        node_by_id[flow.targetRef].type
        for flow in model.sequenceFlows
        if flow.sourceRef == gateway.id
    ]
    assert branch_targets == ["intermediateCatchEvent", "intermediateCatchEvent"]
    # event gateways branch on which event fires, never on a data condition
    assert not any(
        flow.conditionExpression for flow in model.sequenceFlows if flow.sourceRef == gateway.id
    )
    # the "5 giorni" branch is inferred as a timer, the other as a message/plain wait
    catch_defs = {
        node.eventDefinition
        for node in model.flowNodes
        if node.type == "intermediateCatchEvent"
    }
    assert "timer" in catch_defs
    conditional_catches = [
        node
        for node in model.flowNodes
        if node.eventDefinition == "conditional"
    ]
    assert conditional_catches
    assert all(node.eventConditionExpression for node in conditional_catches)

    report = analyze_control_flow(model)
    assert not any(issue.code == "event_gateway_bad_target" for issue in report.errors)
    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:eventBasedGateway" in xml
    assert "<bpmn:conditionalEventDefinition>" in xml
    assert '<bpmn:condition xsi:type="bpmn:tFormalExpression">' in xml
    assert "<bpmn:conditionalEventDefinition />" not in xml


def test_synthetic_catch_events_are_ordered_next_to_their_gateway():
    model = _compile(_process("event_based"))
    order = [node.id for node in model.flowNodes]
    gateway = next(node for node in model.flowNodes if node.type == "eventBasedGateway")
    catch_ids = [
        node.id for node in model.flowNodes if node.type == "intermediateCatchEvent"
    ]
    gateway_rank = order.index(gateway.id)
    # every synthetic catch sits immediately after the gateway, before the tail
    assert [order.index(cid) for cid in catch_ids] == [
        gateway_rank + 1 + offset for offset in range(len(catch_ids))
    ]


def test_synthetic_conditional_catch_without_a_trigger_is_skipped_with_a_warning():
    process = _process("event_based")
    process.flow_edges = [edge for edge in process.flow_edges if edge.id != "E3"]

    model = _compile(process)
    gateway = next(node for node in model.flowNodes if node.type == "eventBasedGateway")
    direct_targets = {
        flow.targetRef for flow in model.sequenceFlows if flow.sourceRef == gateway.id
    }

    assert any(
        node.id in direct_targets and node.name == "Spedisci ordine"
        for node in model.flowNodes
    )
    assert any("senza trigger esplicito" in warning for warning in model.model_warnings)
    assert "<bpmn:conditionalEventDefinition />" not in semantic_model_to_bpmn_xml(model)


def test_soundness_flags_an_event_gateway_wired_straight_to_a_task():
    model = BPMNSemanticModel(
        id="P",
        name="P",
        flowNodes=[
            BPMNFlowNode(id="s", type="startEvent", name="s"),
            BPMNFlowNode(id="g", type="eventBasedGateway", name="g"),
            BPMNFlowNode(id="catch", type="intermediateCatchEvent", name="catch", eventDefinition="message"),
            BPMNFlowNode(id="a", type="task", name="a"),
            BPMNFlowNode(id="b", type="task", name="b"),
            BPMNFlowNode(id="e", type="endEvent", name="e"),
        ],
        sequenceFlows=[
            BPMNSequenceFlow(id="f1", sourceRef="s", targetRef="g"),
            BPMNSequenceFlow(id="f2", sourceRef="g", targetRef="catch"),
            BPMNSequenceFlow(id="f3", sourceRef="g", targetRef="a"),  # illegal: straight to a task
            BPMNSequenceFlow(id="f4", sourceRef="catch", targetRef="b"),
            BPMNSequenceFlow(id="f5", sourceRef="a", targetRef="e"),
            BPMNSequenceFlow(id="f6", sourceRef="b", targetRef="e"),
        ],
    )
    report = analyze_control_flow(model)
    assert any(issue.code == "event_gateway_bad_target" for issue in report.errors)
