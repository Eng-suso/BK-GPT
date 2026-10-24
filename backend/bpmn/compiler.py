"""Compile a `ProcessUnderstanding` into a `BPMNSemanticModel`.

Deterministic: the LLM's semantic judgement is already baked into the
`ProcessUnderstanding`; this module only turns that structure into well-formed
BPMN (chain, gateways, branches, loops, intermediate events, boundary events,
collaboration) and records where every source item landed.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Literal

from backend.bpmn._helpers import (
    actor_label,
    decision_documentation,
    json_documentation,
    source_ref_id,
    step_documentation,
    xml_id,
)
from backend.bpmn.collaboration import (
    build_collaboration_layer,
    finalize_message_flows,
    lane_for_step,
    populate_lane_refs,
    step_is_external_only,
)
from backend.bpmn.compilation_plan import build_bpmn_compilation_plan
from backend.bpmn.data_flow import build_data_flow
from backend.bpmn.flow_registry import FlowRegistry, sequence_flow_edges_by_endpoint
from backend.bpmn.models import (
    ACTIVITY_NODE_TYPES,
    EVENT_DEFINITIONS_BY_NODE_TYPE,
    BPMNAssociation,
    BPMNFlowNode,
    BPMNLane,
    BPMNSemanticModel,
    BPMNSequenceFlow,
)
from backend.process_understanding import (
    ProcessActor,
    ProcessDecision,
    ProcessEvent,
    ProcessExceptionPath,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)

_INTERMEDIATE_EVENT_DEFINITION: dict[str, Literal["timer", "message"] | None] = {
    "timer": "timer",
    "message": "message",
    "intermediate": None,
}

_GATEWAY_BPMN_TYPE: dict[str, str] = {
    "exclusive": "exclusiveGateway",
    "inclusive": "inclusiveGateway",
    "parallel": "parallelGateway",
    "complex": "complexGateway",
    "event_based": "eventBasedGateway",
}

# Gateways whose outgoing flows carry data-based condition expressions. Parallel
# and event-based gateways never do (they fork on tokens / on which event fires).
_DATA_BASED_GATEWAYS = frozenset({"exclusiveGateway", "inclusiveGateway", "complexGateway"})
# Splits that may run several branches at once: where those branches meet again
# a join of the same type waits for them (OMG BPMN 2.0, 10.5.4-10.5.7). An
# exclusive split runs one branch: where its branches (or a rework loop) meet
# again an exclusive merge gateway takes them, never the activity or the end
# event itself (Mendling et al., 7PMG; BEF4LLM syntactic rules 8, 9, 12).
_SYNCHRONIZING_GATEWAYS = frozenset({"parallelGateway", "inclusiveGateway", "complexGateway"})
_SIGNAL_WORDS = ("segnale", "signal", "broadcast")


def _gateway_bpmn_type(decision: ProcessDecision) -> str:
    """Map a ProcessDecision's gateway_type to the corresponding BPMN gateway type.

    Args:
        decision: The ProcessDecision containing the gateway_type.

    Returns:
        A BPMN gateway type string (e.g., "exclusiveGateway", "inclusiveGateway").
    """
    return _GATEWAY_BPMN_TYPE.get(decision.gateway_type, "exclusiveGateway")


def _branch_catch_event_definition(text: str) -> Literal["timer", "message", "signal", "conditional"]:
    """Infer the catch-event trigger for an event-based gateway branch."""
    if _matches_word(text, ("timer", "timeout", "scadenza", "scaduto", "ritardo", "termine", "giorni", "ore")):
        return "timer"
    if _matches_word(text, (*_SIGNAL_WORDS, "evento di sistema")):
        return "signal"
    if _matches_word(text, ("messaggio", "risposta", "notifica", "comunicazione", "riscontro", "email", "conferma")):
        return "message"
    return "conditional"


def build_bpmn_semantic_model(
    *,
    process_id: str,
    process_name: str,
    process: ProcessUnderstanding,
) -> BPMNSemanticModel:
    """
    Compile a process understanding into a lossless BPMN semantic model.
    
    The resulting model preserves source traceability, represents collaboration,
    lanes, nodes, flows, data mappings, warnings, and a compilation plan. The
    function performs no external side effects or persistence.
    
    Args:
        process_id (str): Untrusted source identifier used to derive a safe BPMN
            process identifier.
        process_name (str): Untrusted display name for the BPMN process.
        process (ProcessUnderstanding): Untrusted process definition to compile.
    
    Returns:
        BPMNSemanticModel: The compiled BPMN semantic model with lossless coverage.
    
    Raises:
        ValueError: If the compilation plan reports any coverage losses.
    """
    used_ids: set[str] = set()
    safe_process_id = xml_id(process_id, "Process", used_ids)
    collaboration = build_collaboration_layer(process, safe_process_id, used_ids)
    lanes = collaboration.lanes
    actor_lane_map = collaboration.lane_by_actor_id
    step_by_id = {step.id: step for step in process.steps}
    ordered_chain = _ordered_chain_items(process, step_by_id)

    start_event = next((event for event in process.events if event.type == "start"), None)
    nodes: list[BPMNFlowNode] = [
        BPMNFlowNode(
            id=xml_id("StartEvent_1", "StartEvent", used_ids),
            type="startEvent",
            name=_start_name(process),
            **(
                _event_definition_fields(start_event, "startEvent", start_event.definition)
                if start_event is not None and start_event.definition is not None
                else {"eventDefinition": _start_event_definition(process)}
            ),
        ),
    ]
    warnings = _semantic_warnings(
        process, lanes, collaboration_built=collaboration.collaboration_id is not None
    )
    warnings.extend(collaboration.warnings)
    if process.steps and not (process.main_success_path or process.sequence):
        # Senza un percorso dichiarato i passaggi si incatenano nell'ordine in
        # cui il piano li elenca, e quell'ordine e' un'abitudine di chi scrive,
        # non un'affermazione di una fonte: la fine del percorso normale finisce
        # collegata all'inizio di un ramo d'urgenza. Il disegno resta, ma non in
        # silenzio.
        warnings.append(
            "Percorso principale non dichiarato: l'ordine dei passaggi e' dedotto "
            "dall'ordine in cui il piano li elenca, non da una fonte."
        )
    registry = FlowRegistry(
        used_ids=used_ids,
        edges_by_original=sequence_flow_edges_by_endpoint(process),
    )
    step_node_by_original_id: dict[str, str] = {}
    gateway_by_decision_id: dict[str, BPMNFlowNode] = {}
    gateway_by_step_id: dict[str, BPMNFlowNode] = {}
    instantiating = next(
        (d for d in process.decisions if d.gateway_type == "event_based" and d.instantiate), None
    )
    if instantiating is not None:
        # The first event to arrive creates the instance: the gateway takes the
        # start event's place (OMG BPMN 2.0, 10.5.6).
        nodes.clear()
        _place_gateway(
            instantiating,
            anchor_id=instantiating.id,
            lane_id=None,
            used_ids=used_ids,
            nodes=nodes,
            registry=registry,
            gateway_by_decision_id=gateway_by_decision_id,
            gateway_by_step_id=gateway_by_step_id,
        )
    for event in process.events:
        if event.type == "start":
            registry.map(event.id, nodes[0].id)

    main_chain: list[str] = [nodes[0].id]
    decision_by_anchor_step_id, decision_anchor_warnings = _decision_anchor_map(process, ordered_chain)
    if instantiating is not None:
        decision_by_anchor_step_id = {
            anchor: decision for anchor, decision in decision_by_anchor_step_id.items() if decision is not instantiating
        }
    warnings.extend(decision_anchor_warnings)

    for index, item in enumerate(ordered_chain, start=1):
        if isinstance(item, ProcessEvent):
            event_node = _event_node(item, used_ids)
            nodes.append(event_node)
            main_chain.append(event_node.id)
            step_node_by_original_id[item.id] = event_node.id
            registry.map(item.id, event_node.id)
            _attach_anchored_gateway(
                anchor_id=item.id,
                lane_id=None,
                decision_by_anchor_step_id=decision_by_anchor_step_id,
                used_ids=used_ids,
                nodes=nodes,
                main_chain=main_chain,
                registry=registry,
                gateway_by_decision_id=gateway_by_decision_id,
                gateway_by_step_id=gateway_by_step_id,
            )
            continue

        step = item
        lane_id = lane_for_step(step, process.actors, actor_lane_map)
        if step_is_external_only(step, collaboration.external_actor_ids):
            warnings.append(
                f"Attivita '{step.label}' e assegnata solo a un partecipante esterno: "
                "verificare se appartiene al pool esterno o va resa un message flow."
            )
        task = BPMNFlowNode(
            id=xml_id(step.id or f"Task_{index}", "Task", used_ids),
            type=_task_type(step),
            calledElement=step.called_process if step.type == "call_activity" else None,
            name=step.label,
            laneId=lane_id,
            owner=actor_label(process.actors, step.actor_ids),
            loopCharacteristics=_loop_characteristics(step),
            documentation=step_documentation(step, process.actors),
            sourceRefs=[source_ref_id("steps", step.id)],
        )
        nodes.append(task)
        main_chain.append(task.id)
        step_node_by_original_id[step.id] = task.id
        registry.map(step.id, task.id)
        _attach_anchored_gateway(
            anchor_id=step.id,
            lane_id=lane_id,
            decision_by_anchor_step_id=decision_by_anchor_step_id,
            used_ids=used_ids,
            nodes=nodes,
            main_chain=main_chain,
            registry=registry,
            gateway_by_decision_id=gateway_by_decision_id,
            gateway_by_step_id=gateway_by_step_id,
        )

    end, end_node_by_key = _build_end_events(process, used_ids)
    for end_node in end_node_by_key.values():
        if end_node not in nodes:
            nodes.append(end_node)
    if end not in nodes:
        nodes.append(end)
    main_chain.append(end.id)
    for event in process.events:
        if event.type == "end" and event.id in end_node_by_key:
            registry.map(event.id, end_node_by_key[event.id].id)

    registry.connect_chain(main_chain)

    _add_alternative_paths(
        process=process,
        nodes=nodes,
        registry=registry,
        used_ids=used_ids,
        step_by_id=step_by_id,
        step_node_by_original_id=step_node_by_original_id,
        gateway_by_decision_id=gateway_by_decision_id,
        gateway_by_step_id=gateway_by_step_id,
        end_node_by_key=end_node_by_key,
        primary_end=end,
        decision_by_anchor_step_id=decision_by_anchor_step_id,
        actors=process.actors,
        actor_lane_map=actor_lane_map,
        warnings=warnings,
    )
    _add_loop_flows(
        process=process,
        registry=registry,
        nodes=nodes,
        step_node_by_original_id=step_node_by_original_id,
        used_ids=used_ids,
        warnings=warnings,
    )
    _complete_flow_graph(process, registry, nodes, warnings)
    declared_defaults = _label_decision_outcomes(process, registry, gateway_by_decision_id)
    detached_associations = _add_detached_activities(
        process=process,
        nodes=nodes,
        step_node_by_original_id=step_node_by_original_id,
        actor_lane_map=actor_lane_map,
        used_ids=used_ids,
        warnings=warnings,
    )
    _add_boundary_events(
        process=process,
        registry=registry,
        nodes=nodes,
        step_node_by_original_id=step_node_by_original_id,
        step_by_id=step_by_id,
        actor_lane_map=actor_lane_map,
        actors=process.actors,
        used_ids=used_ids,
        end_id=end.id,
        warnings=warnings,
    )
    registry.apply_edge_overlay()
    _cut_at_links(nodes, registry)
    _add_synchronizing_joins(nodes, registry, gateway_by_decision_id, used_ids)
    _normalize_event_gateways(nodes, registry, used_ids, warnings)
    _add_exclusive_merges(nodes, registry, used_ids)
    flows = registry.flows
    _assign_gateway_defaults(nodes, flows, warnings, declared_default_ids={flow.id for flow in declared_defaults})
    populate_lane_refs(lanes, nodes)
    message_flows = finalize_message_flows(
        collaboration=collaboration,
        step_node_by_original_id=step_node_by_original_id,
        node_ids={node.id for node in nodes},
        used_ids=used_ids,
        warnings=warnings,
    )
    data_flow = build_data_flow(
        process, step_node_by_original_id=step_node_by_original_id, used_ids=used_ids
    )

    model = BPMNSemanticModel(
        id=safe_process_id,
        name=process_name,
        collaborationId=collaboration.collaboration_id,
        participants=collaboration.participants,
        lanes=[lane for lane in lanes if lane.flowNodeRefs],
        flowNodes=nodes,
        sequenceFlows=flows,
        messageFlows=message_flows,
        dataObjects=data_flow.data_objects,
        dataStores=data_flow.data_stores,
        textAnnotations=[],
        associations=[*data_flow.associations, *detached_associations],
        model_warnings=warnings,
        sourceProcessUnderstanding=process.model_dump(mode="json"),
    )
    model.compilationPlan = build_bpmn_compilation_plan(
        process_id=safe_process_id,
        process_name=process_name,
        process=process,
        model=model,
    )
    if model.compilationPlan.coverage.losses:
        raise ValueError(
            "Compilazione BPMN non lossless: " + "; ".join(model.compilationPlan.coverage.losses)
        )
    return model


def _task_type(step: ProcessStep) -> str:
    """Map a process step to its corresponding BPMN task type.
    
    Args:
        step: The process step to classify.
    
    Returns:
        The mapped BPMN task type, or ``"userTask"`` when the step type is
        unrecognized.
    """
    return {
        "user_task": "userTask",
        "manual_task": "manualTask",
        "service_task": "serviceTask",
        "send_task": "sendTask",
        "receive_task": "receiveTask",
        "business_rule_task": "businessRuleTask",
        "script_task": "scriptTask",
        "subprocess": "subProcess",
        "call_activity": "callActivity",
        "transaction": "transaction",
        "ad_hoc_subprocess": "adHocSubProcess",
        "event_subprocess": "subProcess",
    }.get(step.type, "userTask")


def _detached(step: ProcessStep) -> bool:
    """A step started by an event rather than by the flow: an event sub-process or a compensation."""
    return step.type == "event_subprocess" or bool(step.compensates_step_id)


def _loop_characteristics(
    step: ProcessStep,
) -> Literal["none", "multiInstanceSequential", "multiInstanceParallel"]:
    """
    Map a step's multiplicity to its BPMN multi-instance loop marker.
    
    Args:
        step: Process-step input whose typed multiplicity determines the marker.
    
    Returns:
        The multi-instance marker for sequential or parallel multiplicity, or
        ``"none"`` when the step has no recognized multi-instance multiplicity.
    """
    if step.multiplicity == "per_item":
        return "multiInstanceParallel"
    if step.multiplicity == "per_item_sequential":
        return "multiInstanceSequential"
    return "none"


def _ordered_chain_items(
    process: ProcessUnderstanding,
    step_by_id: dict[str, ProcessStep],
) -> list[ProcessStep | ProcessEvent]:
    """Builds the ordered main-process chain from steps and intermediate flow events.
    
    The result preserves the declared main path or sequence when available, falls
    back to all process steps when no chain items are found, and inserts eligible
    intermediate events after their placed flow-edge predecessors. Unplaced events
    without a placed predecessor are omitted.
    
    Args:
        process: Untrusted process data containing steps, events, paths, and flow
            edges.
        step_by_id: Mapping from step identifiers to their corresponding process
            steps.
    
    Returns:
        The ordered process steps and intermediate timer or message events.
    """
    flow_event_by_id = {
        event.id: event
        for event in process.events
        if event.id and event.type in _INTERMEDIATE_EVENT_DEFINITION
    }
    chain: list[ProcessStep | ProcessEvent] = []
    for item_id in process.main_success_path or process.sequence:
        if item_id in step_by_id and not _detached(step_by_id[item_id]):
            chain.append(step_by_id[item_id])
        elif item_id in flow_event_by_id:
            chain.append(flow_event_by_id[item_id])
    if not chain:
        chain = [step for step in process.steps if not _detached(step)]

    placed = {item.id for item in chain}
    progressed = True
    while progressed:
        progressed = False
        for event in flow_event_by_id.values():
            if event.id in placed:
                continue
            predecessor = next(
                (
                    edge.source_id
                    for edge in process.flow_edges
                    if edge.target_id == event.id and edge.source_id in placed
                ),
                None,
            )
            if predecessor is None:
                continue
            insert_at = next(index for index, item in enumerate(chain) if item.id == predecessor) + 1
            chain.insert(insert_at, event)
            placed.add(event.id)
            progressed = True
    return chain


def _attach_anchored_gateway(
    *,
    anchor_id: str,
    lane_id: str | None,
    decision_by_anchor_step_id: dict[str, ProcessDecision],
    used_ids: set[str],
    nodes: list[BPMNFlowNode],
    main_chain: list[str],
    registry: FlowRegistry,
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    gateway_by_step_id: dict[str, BPMNFlowNode],
) -> None:
    """Attach a decision gateway immediately after its anchor step in the main chain.

    Args:
        anchor_id: The ID of the anchor step or event.
        lane_id: The lane ID to assign to the gateway, if any.
        decision_by_anchor_step_id: Mapping of anchor step IDs to their decisions.
        used_ids: Set of already-allocated IDs.
        nodes: List of BPMN flow nodes to append the gateway to.
        main_chain: List of node IDs forming the main process chain.
        registry: FlowRegistry for tracking node mappings.
        gateway_by_decision_id: Dictionary to populate with decision ID to gateway mappings.
        gateway_by_step_id: Dictionary to populate with step ID to gateway mappings.
    """
    decision = decision_by_anchor_step_id.get(anchor_id)
    if decision is None:
        return
    gateway = _place_gateway(
        decision,
        anchor_id=anchor_id,
        lane_id=lane_id,
        used_ids=used_ids,
        nodes=nodes,
        registry=registry,
        gateway_by_decision_id=gateway_by_decision_id,
        gateway_by_step_id=gateway_by_step_id,
    )
    main_chain.append(gateway.id)


def _place_gateway(
    decision: ProcessDecision,
    *,
    anchor_id: str,
    lane_id: str | None,
    used_ids: set[str],
    nodes: list[BPMNFlowNode],
    registry: FlowRegistry,
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    gateway_by_step_id: dict[str, BPMNFlowNode],
) -> BPMNFlowNode:
    """Create a decision's gateway after its anchor step and register it everywhere it is looked up."""
    gateway_type = _gateway_bpmn_type(decision)
    instantiate = gateway_type == "eventBasedGateway" and decision.instantiate
    gateway = BPMNFlowNode(
        id=xml_id(decision.id, "Gateway", used_ids),
        type=gateway_type,
        name=decision.label,
        laneId=lane_id,
        activationCondition=(decision.activation_condition or None) if gateway_type == "complexGateway" else None,
        instantiate=instantiate,
        eventGatewayType="Parallel" if instantiate and decision.event_gateway_type == "parallel" else "Exclusive",
        documentation=decision_documentation(decision),
        sourceRefs=[source_ref_id("decisions", decision.id)],
    )
    nodes.append(gateway)
    registry.map(decision.id, gateway.id)
    if gateway.type in _DATA_BASED_GATEWAYS:
        registry.gateway_ids.add(gateway.id)
    gateway_by_decision_id[decision.id] = gateway
    gateway_by_step_id[anchor_id] = gateway
    return gateway


def _event_node(event: ProcessEvent, used_ids: set[str]) -> BPMNFlowNode:
    """Create a BPMN intermediate event node from a ProcessEvent.

    A throwing event (the process emits a message/signal) becomes an
    `intermediateThrowEvent`; everything else waits and becomes an
    `intermediateCatchEvent`.
    """
    definition = _INTERMEDIATE_EVENT_DEFINITION.get(event.type) if event.definition is None else event.definition
    catches = EVENT_DEFINITIONS_BY_NODE_TYPE["intermediateCatchEvent"]
    throws = EVENT_DEFINITIONS_BY_NODE_TYPE["intermediateThrowEvent"]
    # A definition only one side can carry decides the side: a timer is always
    # waited for, an escalation or a compensation is always thrown.
    if definition in catches and definition not in throws:
        node_type = "intermediateCatchEvent"
    elif definition in throws and definition not in catches:
        node_type = "intermediateThrowEvent"
    else:
        node_type = "intermediateThrowEvent" if event.direction == "throw" else "intermediateCatchEvent"
    return BPMNFlowNode(
        id=xml_id(event.id or "IntermediateEvent", "IntermediateEvent", used_ids),
        type=node_type,
        name=event.label,
        **_event_definition_fields(event, node_type, definition),
        documentation=json_documentation(
            "event",
            {"type": event.type, "timing": event.timing, "source_evidence": event.source_evidence},
        ),
        sourceRefs=[source_ref_id("events", event.id)],
    )


def _event_definition_fields(event: ProcessEvent, node_type: str, definition: str | None) -> dict:
    """The BPMNFlowNode fields for `definition` on a `node_type`, or none when it does not fit there.

    A definition the event cannot carry (an error on a start event, a multiple
    event with a single trigger, a condition without its expression) is left
    out rather than drawn wrong; the event stays a plain one.
    """
    if definition in (None, "none") or definition not in EVENT_DEFINITIONS_BY_NODE_TYPE.get(node_type, ()):
        return {}
    if definition == "multiple":
        triggers = list(dict.fromkeys(event.triggers))
        if len(triggers) < 2:
            return {}
        catches = node_type in {"startEvent", "intermediateCatchEvent", "boundaryEvent"}
        return {
            "eventDefinition": "multiple",
            "triggers": triggers,
            "parallelMultiple": event.parallel_multiple and catches,
            "eventConditionExpression": event.condition if "conditional" in triggers else None,
        }
    if definition == "conditional":
        return {"eventDefinition": "conditional", "eventConditionExpression": event.condition} if event.condition else {}
    return {"eventDefinition": definition}


def _add_detached_activities(
    *,
    process: ProcessUnderstanding,
    nodes: list[BPMNFlowNode],
    step_node_by_original_id: dict[str, str],
    actor_lane_map: dict[str, str],
    used_ids: set[str],
    warnings: list[str],
) -> list[BPMNAssociation]:
    """Draw the steps an event starts instead of the flow.

    An event sub-process runs whenever its trigger occurs (OMG BPMN 2.0, 10.3.6).
    A compensation activity undoes a completed step: a compensation boundary
    event on that step points to it through an association, never a sequence
    flow (10.6).

    Returns:
        The associations from compensation boundary events to their activities.
    """
    associations: list[BPMNAssociation] = []
    for step in process.steps:
        if not _detached(step):
            continue
        lane_id = lane_for_step(step, process.actors, actor_lane_map)
        if step.type == "event_subprocess":
            start_definition = step.event_trigger
            if start_definition is None or (start_definition == "conditional" and not step.event_condition):
                warnings.append(f"Event sub-process '{step.label}' senza trigger esplicito: non disegnato.")
                continue
            node = BPMNFlowNode(
                id=xml_id(step.id, "EventSubProcess", used_ids),
                type="subProcess",
                name=step.label,
                laneId=lane_id,
                triggeredByEvent=True,
                eventSubProcessStart=BPMNFlowNode(
                    id=xml_id(f"{step.id}_Start", "StartEvent", used_ids),
                    type="startEvent",
                    name=step.label,
                    eventDefinition=start_definition,
                    eventConditionExpression=step.event_condition if start_definition == "conditional" else None,
                    isInterrupting=step.interrupting,
                ),
                documentation=step_documentation(step, process.actors),
                sourceRefs=[source_ref_id("steps", step.id)],
            )
            nodes.append(node)
            step_node_by_original_id[step.id] = node.id
            continue

        compensated = step_node_by_original_id.get(step.compensates_step_id or "")
        if compensated is None:
            warnings.append(
                f"Compensazione '{step.label}': il passo da compensare '{step.compensates_step_id}' non e' disegnato."
            )
            continue
        handler = BPMNFlowNode(
            id=xml_id(step.id, "Task", used_ids),
            type=_task_type(step),
            name=step.label,
            laneId=lane_id,
            owner=actor_label(process.actors, step.actor_ids),
            isForCompensation=True,
            documentation=step_documentation(step, process.actors),
            sourceRefs=[source_ref_id("steps", step.id)],
        )
        boundary = BPMNFlowNode(
            id=xml_id(f"{step.id}_Compensation", "BoundaryEvent", used_ids),
            type="boundaryEvent",
            name="",
            laneId=next((node.laneId for node in nodes if node.id == compensated), lane_id),
            attachedToRef=compensated,
            eventDefinition="compensation",
        )
        nodes.extend([boundary, handler])
        step_node_by_original_id[step.id] = handler.id
        associations.append(
            BPMNAssociation(
                id=xml_id(f"{boundary.id}_to_{handler.id}", "Association", used_ids),
                sourceRef=boundary.id,
                targetRef=handler.id,
                direction="one",
            )
        )
    return associations


def _cut_at_links(nodes: list[BPMNFlowNode], registry: FlowRegistry) -> None:
    """A link throw ends a stretch of the flow and its catch starts the next one.

    The chain drew a flow into every node; the pair stands in for it (OMG BPMN
    2.0, 10.4.5), so nothing leaves a link throw and nothing enters a link catch.
    """
    throws = {node.id for node in nodes if node.type == "intermediateThrowEvent" and node.eventDefinition == "link"}
    catches = {node.id for node in nodes if node.type == "intermediateCatchEvent" and node.eventDefinition == "link"}
    for flow in [f for f in registry.flows if f.sourceRef in throws or f.targetRef in catches]:
        registry.remove(flow)


def _decision_anchor_map(
    process: ProcessUnderstanding,
    ordered_chain: list[ProcessStep | ProcessEvent],
) -> tuple[dict[str, ProcessDecision], list[str]]:
    """Anchor each decision to the step that flows into it.

    A main-path step wins; otherwise the anchor may be a step of an alternative
    path (e.g. review -> "review successful?"), placed when that branch is drawn.

    Returns:
        The decisions by anchor step, and the warnings.
    """
    main_step_ids = [item.id for item in ordered_chain if item.id]
    all_step_ids = [*main_step_ids, *(step.id for step in process.steps)]
    decision_by_anchor: dict[str, ProcessDecision] = {}
    warnings: list[str] = []
    unassigned = list(process.decisions)

    def anchor_for(decision: ProcessDecision) -> str | None:
        return _anchor_step_for_decision(process, decision, main_step_ids) or _anchor_step_for_decision(
            process, decision, all_step_ids
        )

    for path in process.alternative_paths:
        decision = _decision_for_path(path, unassigned)
        if decision is None:
            continue
        anchor_step_id = anchor_for(decision)
        if anchor_step_id is None:
            continue
        if anchor_step_id in decision_by_anchor:
            warnings.append(
                f"Piu' decisioni candidate sullo stesso step '{anchor_step_id}'; verificare il modello."
            )
            continue
        decision_by_anchor[anchor_step_id] = decision
        unassigned = [item for item in unassigned if item.id != decision.id]

    for decision in unassigned:
        anchor_step_id = anchor_for(decision)
        if anchor_step_id and anchor_step_id not in decision_by_anchor:
            decision_by_anchor[anchor_step_id] = decision

    return decision_by_anchor, warnings


def _decision_for_path(path, decisions: list[ProcessDecision]) -> ProcessDecision | None:
    """Find the decision that leads to a given alternative path.

    Args:
        path: The alternative path to match.
        decisions: List of ProcessDecision instances to search.

    Returns:
        The matching ProcessDecision, or None if not found.
    """
    for decision in decisions:
        if any(outcome.target_path_id == path.id for outcome in decision.outcome_details):
            return decision
    return None


def _anchor_step_for_decision(
    process: ProcessUnderstanding,
    decision: ProcessDecision,
    ordered_step_ids: list[str],
) -> str | None:
    """Find the step, among `ordered_step_ids`, that a flow edge leads into the decision from.

    Args:
        process: The ProcessUnderstanding model.
        decision: The ProcessDecision to find an anchor for.
        ordered_step_ids: The candidate anchor step IDs.

    Returns:
        The ID of the anchor step, or None if not found.
    """
    for edge in process.flow_edges:
        if edge.target_id == decision.id and edge.source_id in ordered_step_ids:
            return edge.source_id
    return None


def _add_alternative_paths(
    *,
    process: ProcessUnderstanding,
    nodes: list[BPMNFlowNode],
    registry: FlowRegistry,
    used_ids: set[str],
    step_by_id: dict[str, ProcessStep],
    step_node_by_original_id: dict[str, str],
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    gateway_by_step_id: dict[str, BPMNFlowNode],
    end_node_by_key: dict[str, BPMNFlowNode],
    primary_end: BPMNFlowNode,
    decision_by_anchor_step_id: dict[str, ProcessDecision],
    actors: list[ProcessActor],
    actor_lane_map: dict[str, str],
    warnings: list[str],
) -> None:
    """Add BPMN branches for decision-linked alternative paths.
    
    The function appends branch activities and sequence flows, resolves branch
    rejoins or end events, and records warnings for missing, incomplete,
    unconfirmed, or unlinked paths. Alternative path data in ``process`` is
    treated as untrusted input; unresolved step references are skipped without
    raising an exception.
    
    Args:
        process: Untrusted process data containing decisions and alternative paths.
        nodes: Node collection to mutate with generated branch activities.
        registry: Flow registry to mutate with branch mappings and sequence flows.
        used_ids: Allocated XML identifiers to update.
        step_by_id: Mapping of source step identifiers to process steps.
        step_node_by_original_id: Mapping of source step identifiers to compiled
            node identifiers.
        gateway_by_decision_id: Decision gateway mapping.
        gateway_by_step_id: Gateways anchored to source steps.
        end_node_by_key: End-event mapping used to resolve branch destinations.
        primary_end: Default end event for unresolved branch destinations.
        decision_by_anchor_step_id: Decisions by anchor step. One anchored to a
            branch step becomes a gateway on that branch (e.g. review ->
            "review successful?") and its own paths are compiled the same way.
        actors: Process actors used for branch ownership and lane assignment.
        actor_lane_map: Mapping of actor identifiers to lane identifiers.
        warnings: Warning collection to mutate.
    
    Side Effects:
        Mutates ``nodes``, ``registry``, ``used_ids``, and ``warnings``. Does not
        persist data or raise errors for malformed or unresolved alternative paths.
    """
    unassigned_paths = list(process.alternative_paths)
    gateways = list(gateway_by_decision_id.values())
    pending = deque(decision for decision in process.decisions if decision.id in gateway_by_decision_id)

    while pending:
        decision = pending.popleft()
        gateway = gateway_by_decision_id[decision.id]

        # Tutti i percorsi che la decisione nomina, non il primo. Una scelta a tre
        # vie - richiesta incompleta, serve un'autorizzazione, si procede - e' una
        # decisione con due rami alternativi piu' il percorso principale: prendere
        # solo il primo ramo perdeva l'altro senza che la compilazione lo dicesse,
        # cioe' un disegno "lossless" con un pezzo di processo in meno.
        paths = _take_alternative_paths_for_decision(decision, unassigned_paths)
        if not paths:
            warnings.append(f"Gateway '{decision.label}' senza alternative path esplicito collegato.")
            continue

        for path in paths:
            if not path.sequence and not path.ends_at:
                warnings.append(f"Alternative path '{path.label}' senza sequenza o fine esplicita.")
                continue

            outcome_name = _outcome_name_for_path(decision, path)
            previous_id = gateway.id
            for branch_index, step_id in enumerate(path.sequence, start=1):
                if step_id == path.rejoins_at and step_id in step_node_by_original_id:
                    continue
                source_step = step_by_id.get(step_id)
                if source_step is None:
                    warnings.append(f"Alternative path '{path.label}' cita step non trovato: {step_id}")
                    continue
                lane_id = lane_for_step(source_step, actors, actor_lane_map)
                branch_node = BPMNFlowNode(
                    id=xml_id(f"{path.id}_{source_step.id or branch_index}", "Task", used_ids),
                    type=_task_type(source_step),
                    calledElement=source_step.called_process if source_step.type == "call_activity" else None,
                    name=source_step.label,
                    laneId=lane_id,
                    owner=actor_label(actors, source_step.actor_ids),
                    loopCharacteristics=_loop_characteristics(source_step),
                )
                nodes.append(branch_node)
                registry.map(source_step.id, branch_node.id)
                _link_branch(registry, path.id, gateway.id, previous_id, branch_node.id, outcome_name)
                previous_id = branch_node.id

                follow_up = decision_by_anchor_step_id.get(source_step.id)
                if follow_up is not None and follow_up.id not in gateway_by_decision_id:
                    follow_gateway = _place_gateway(
                        follow_up,
                        anchor_id=source_step.id,
                        lane_id=lane_id,
                        used_ids=used_ids,
                        nodes=nodes,
                        registry=registry,
                        gateway_by_decision_id=gateway_by_decision_id,
                        gateway_by_step_id=gateway_by_step_id,
                    )
                    registry.add(branch_node.id, follow_gateway.id)
                    for outcome in follow_up.outcome_details:
                        target = registry.compiled_for(outcome.target_ref or "")
                        if target:
                            registry.add(follow_gateway.id, target)
                    pending.append(follow_up)
                    if step_id != path.sequence[-1]:
                        warnings.append(
                            f"Alternative path '{path.label}': i passi dopo '{source_step.label}' seguono "
                            f"la decisione '{follow_up.label}' e non sono stati disegnati."
                        )
                    break
            else:
                # No decision carries the branch on: it rejoins or ends here.
                if path.rejoins_at and path.rejoins_at in step_node_by_original_id:
                    exit_target = step_node_by_original_id[path.rejoins_at]
                elif path.ends_at and path.ends_at in step_node_by_original_id:
                    exit_target = step_node_by_original_id[path.ends_at]
                else:
                    if not path.ends_at:
                        warnings.append(
                            f"Alternative path '{path.label}' senza rientro ne' fine esplicita: chiuso sulla "
                            f"fine principale '{primary_end.name}'; verificare l'esito."
                        )
                    exit_target = _resolve_alt_path_end(
                        path, outcome_name, gateway.laneId, end_node_by_key, primary_end, nodes, used_ids
                    )
                _link_branch(
                    registry, path.id, gateway.id, previous_id, exit_target, outcome_name, path.trigger_or_condition
                )

            if not path.is_confirmed:
                warnings.append(f"Alternative path '{path.label}' non confermato.")

    for decision in process.decisions:
        if decision.id not in gateway_by_decision_id:
            warnings.append(f"Decisione '{decision.label}' non mappabile: manca anchor esplicito in flow_edges.")
    if unassigned_paths and not gateways:
        warnings.append("Alternative path presenti, ma nessun gateway decisionale e' stato generato.")
    elif unassigned_paths:
        for path in unassigned_paths:
            warnings.append(f"Alternative path '{path.label}' non collegato a un outcome decisionale esplicito.")


def _link_branch(
    registry: FlowRegistry,
    path_id: str,
    gateway_id: str,
    source: str,
    target: str,
    outcome_name: str | None,
    name: str | None = None,
) -> None:
    """Draw one flow of a branch.

    The flow leaving the gateway is the outcome itself: it takes the outcome's
    name and marks where the path starts, so a flow edge naming the path resolves.
    """
    leaves_gateway = source == gateway_id
    registry.add(source, target, name=outcome_name if leaves_gateway else name)
    if leaves_gateway:
        registry.map(path_id, target)


def _resolve_alt_path_end(
    path,
    outcome_name: str | None,
    lane_id: str | None,
    end_node_by_key: dict[str, BPMNFlowNode],
    primary_end: BPMNFlowNode,
    nodes: list[BPMNFlowNode],
    used_ids: set[str],
) -> str:
    """Resolve the end node ID for an alternative path.

    Routes to an existing end event if `ends_at` names one, otherwise creates a new end event.

    Args:
        path: The alternative path with an ends_at field.
        outcome_name: The name of the decision outcome leading to this path.
        lane_id: The lane ID for any synthesized end event.
        end_node_by_key: Dictionary of existing end events keyed by ID or normalized label.
        primary_end: The primary end event to use as default.
        nodes: List of BPMN flow nodes to append any synthesized end to.
        used_ids: Set of already-allocated IDs.

    Returns:
        The ID of the resolved or newly created end event.
    """
    target = path.ends_at
    if target and (target in end_node_by_key or _norm_end_key(target) in end_node_by_key):
        return _end_for(target, end_node_by_key, primary_end).id
    if not target:
        return primary_end.id
    synth = BPMNFlowNode(
        id=xml_id(f"End_{path.id}", "EndEvent", used_ids),
        type="endEvent",
        name=target or path.label or outcome_name or "Fine percorso alternativo",
        laneId=lane_id,
    )
    nodes.append(synth)
    end_node_by_key[_norm_end_key(target)] = synth
    return synth.id


def _take_alternative_paths_for_decision(
    decision: ProcessDecision, paths: list[ProcessPath]
) -> list[ProcessPath]:
    """Find and remove every alternative path that a decision's outcomes name.

    Args:
        decision: The ProcessDecision to match against.
        paths: List of alternative paths to search and modify.

    Returns:
        The matching alternative paths in declaration order (removed from the
        list); empty when the decision names none.
    """
    taken = [path for path in paths if _path_matches_decision(decision, path)]
    for path in taken:
        paths.remove(path)
    return taken


def _path_matches_decision(decision, path) -> bool:
    """Check if an alternative path matches a decision's outcomes.

    Args:
        decision: The ProcessDecision with outcome_details.
        path: The alternative path with an id to match.

    Returns:
        True if any outcome in the decision targets this path, False otherwise.
    """
    return any(outcome.target_path_id == path.id for outcome in decision.outcome_details)


def _add_loop_flows(
    *,
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    nodes: list[BPMNFlowNode],
    step_node_by_original_id: dict[str, str],
    used_ids: set[str],
    warnings: list[str],
) -> None:
    """Adds BPMN loop behavior for mapped process loops.
    
    Single-step loops are represented with standard loop characteristics. Multi-step
    loops receive a direct back-edge when the tail has no outgoing flow; otherwise,
    an exclusive gateway is inserted to select repetition or the default exit.
    Unmappable loops are reported through ``warnings``.
    
    Args:
        process (ProcessUnderstanding): Untrusted process input containing loop
            definitions.
        registry (FlowRegistry): Flow registry to update with loop sequence flows
            and gateway mappings.
        nodes (list[BPMNFlowNode]): Mutable BPMN node list in which synthesized loop
            gateways are inserted.
        step_node_by_original_id (dict[str, str]): Mapping from source step IDs to
            compiled BPMN node IDs.
        used_ids (set[str]): Mutable set of allocated IDs used to avoid collisions.
        warnings (list[str]): Mutable collection receiving warnings for loops that
            cannot be mapped or represented.
    
    Side Effects:
        Mutates ``registry``, ``nodes``, ``used_ids`` indirectly through ID
        allocation, and the affected BPMN nodes and ``warnings`` list. It does not
        persist data.
    
    Raises:
        No exceptions are raised explicitly; invalid or incomplete loop mappings
        are reported through ``warnings``.
    """
    node_by_id = {node.id: node for node in nodes}
    for loop in process.loops:
        repeated = [step_id for step_id in loop.repeated_steps if step_id in step_node_by_original_id]
        if len(repeated) == 1:
            # A single repeated activity is a self-loop, not a back-edge through
            # earlier steps: render it as a standard-loop activity marker.
            node = node_by_id.get(step_node_by_original_id[repeated[0]])
            if node is None:
                continue
            if node.loopCharacteristics != "none":
                warnings.append(
                    f"Loop '{loop.label}' sullo step '{node.name}' che e' gia' un'attivita "
                    "multi-instance: marker standardLoop non applicato."
                )
                continue
            node.loopCharacteristics = "standardLoop"
            # loopCondition is "keep iterating while true"; exit_condition is its
            # negation, so it is kept as metadata only, never used as the condition.
            node.loopConditionExpression = loop.condition
            if not loop.condition and loop.exit_condition:
                warnings.append(
                    f"Loop '{loop.label}': manca una condizione di continuazione esplicita "
                    "(solo exit_condition), standardLoop reso senza loopCondition."
                )
            ref = source_ref_id("loops", loop.id)
            if ref not in node.sourceRefs:
                node.sourceRefs.append(ref)
            continue
        if len(repeated) < 2:
            warnings.append(f"Loop '{loop.label}' presente ma non mappabile su almeno due step.")
            continue
        tail = step_node_by_original_id[repeated[-1]]
        head = step_node_by_original_id[repeated[0]]
        loop_doc = json_documentation(
            "loop",
            {
                "label": loop.label,
                "condition": loop.condition,
                "exit_condition": loop.exit_condition,
                "repeated_steps": loop.repeated_steps,
            },
        )
        loop_refs = [source_ref_id("loops", loop.id)]

        forward = [flow for flow in registry.flows if flow.sourceRef == tail]
        if not forward:
            # tail already ends the branch: a plain back-edge is the best we can do
            if registry.add(tail, head, name=loop.condition or loop.label, documentation=loop_doc, source_refs=loop_refs) is None:
                warnings.append(f"Loop '{loop.label}' degenere (rientro su se stesso): non reso come freccia.")
            continue

        # Splice an exclusive gateway in front of `tail`'s exit: one branch repeats
        # the loop body, the (default) branch leaves it.
        gateway = BPMNFlowNode(
            id=xml_id(f"{loop.id}_LoopGateway", "Gateway", used_ids),
            type="exclusiveGateway",
            name=loop.exit_condition or f"Ripetere: {loop.label}?",
            laneId=node_by_id[tail].laneId if tail in node_by_id else None,
            documentation=loop_doc,
            sourceRefs=loop_refs,
        )
        insert_at = next((i for i, node in enumerate(nodes) if node.id == tail), len(nodes) - 1) + 1
        nodes.insert(insert_at, gateway)
        node_by_id[gateway.id] = gateway
        registry.map(loop.id, gateway.id)
        registry.gateway_ids.add(gateway.id)

        exit_flows = registry.reroute_source(tail, gateway.id)
        registry.add(tail, gateway.id)
        loop_flow = registry.add(
            gateway.id, head, name=loop.condition or f"Ripeti {loop.label}", documentation=loop_doc, source_refs=loop_refs
        )
        if loop_flow is not None and loop.condition:
            loop_flow.conditionExpression = loop.condition
        if exit_flows:
            gateway.defaultFlowId = exit_flows[0].id


def _add_boundary_events(
    *,
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    nodes: list[BPMNFlowNode],
    step_node_by_original_id: dict[str, str],
    step_by_id: dict[str, ProcessStep],
    actor_lane_map: dict[str, str],
    actors: list[ProcessActor],
    used_ids: set[str],
    end_id: str,
    warnings: list[str],
) -> None:
    """Add boundary events (error, timer, message, conditional) attached to activities.

    Args:
        process: The ProcessUnderstanding containing exception definitions.
        registry: FlowRegistry for adding exception handler flows.
        nodes: List of BPMN flow nodes to append boundary events and handlers to.
        step_node_by_original_id: Mapping of source step IDs to compiled node IDs.
        step_by_id: Mapping of step IDs to ProcessStep instances.
        actor_lane_map: Mapping of actor IDs to lane IDs.
        actors: List of process actors.
        used_ids: Set of already-allocated IDs.
        end_id: The ID of the primary end event for unhandled exceptions.
        warnings: List to append warning messages to.
    """
    node_type_by_id = {node.id: node.type for node in nodes}
    node_lane_by_id = {node.id: node.laneId for node in nodes}
    node_type_by_id = {node.id: node.type for node in nodes}

    for index, exception in enumerate(process.exceptions, start=1):
        exception_id = exception.id or f"Exception_{index}"
        attached = _exception_attached_node(
            exception, process, registry, step_node_by_original_id, node_type_by_id
        )
        if attached is None:
            warnings.append(
                f"Eccezione '{exception.label}' senza attivita di aggancio valida: non resa come boundary event."
            )
            continue

        definition, interrupting = _exception_event_definition(exception)
        condition_expression = (exception.trigger or "").strip() or None
        if definition == "conditional" and condition_expression is None:
            warnings.append(
                f"Eccezione '{exception.label}' senza trigger esplicito: "
                "boundary event condizionale non generato."
            )
            continue
        if definition == "cancel" and node_type_by_id.get(attached) != "transaction":
            warnings.append(
                f"Eccezione '{exception.label}': l'annullamento vale solo su una transazione, "
                "boundary event non generato."
            )
            continue
        if interrupting != exception.interrupting:
            warnings.append(
                f"Eccezione '{exception.label}': forzata a interrupting perche' un evento "
                f"di tipo '{definition}' non puo' essere non-interrupting."
            )

        boundary = BPMNFlowNode(
            id=xml_id(f"{exception_id}_Boundary", "BoundaryEvent", used_ids),
            type="boundaryEvent",
            name=exception.label,
            laneId=node_lane_by_id.get(attached),
            attachedToRef=attached,
            cancelActivity=interrupting,
            eventDefinition=definition,
            eventConditionExpression=(
                condition_expression if definition == "conditional" else None
            ),
            documentation=json_documentation(
                "exception",
                {
                    "trigger": exception.trigger,
                    "handling": exception.handling,
                    "is_defined": exception.is_defined,
                },
            ),
            sourceRefs=[source_ref_id("exceptions", exception_id)],
        )
        nodes.append(boundary)
        registry.map(exception_id, boundary.id)

        rejoin = _exception_rejoin_node(
            exception,
            process,
            registry,
            step_by_id=step_by_id,
            actor_lane_map=actor_lane_map,
            actors=actors,
            nodes=nodes,
            used_ids=used_ids,
            end_id=end_id,
            exception_source_ref=source_ref_id("exceptions", exception_id),
        )
        if rejoin is not None and rejoin != boundary.id:
            registry.add(boundary.id, rejoin)
        elif exception.handling:
            handler_lane = node_lane_by_id.get(attached)
            handler = BPMNFlowNode(
                id=xml_id(f"{exception_id}_Handler", "Task", used_ids),
                type="task",
                name=exception.handling[:80],
                laneId=handler_lane,
                sourceRefs=[source_ref_id("exceptions", exception_id)],
            )
            handler_end = BPMNFlowNode(
                id=xml_id(f"{exception_id}_End", "EndEvent", used_ids),
                type="endEvent",
                name=exception.label or "Fine gestione eccezione",
                laneId=handler_lane,
            )
            nodes.append(handler)
            nodes.append(handler_end)
            registry.add(boundary.id, handler.id)
            registry.add(handler.id, handler_end.id)
        else:
            registry.add(boundary.id, end_id)
            warnings.append(
                f"Eccezione '{exception.label}' senza gestione definita: boundary event collegato alla fine."
            )

        if not exception.is_defined:
            warnings.append(f"Eccezione '{exception.label}': gestione da definire nel modello.")


def _exception_attached_node(
    exception: ProcessExceptionPath,
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    step_node_by_original_id: dict[str, str],
    node_type_by_id: dict[str, str],
) -> str | None:
    """Find the activity node to which a boundary event should be attached.

    Args:
        exception: The ProcessExceptionPath defining the boundary event.
        process: The ProcessUnderstanding containing flow edges.
        registry: FlowRegistry for resolving compiled node IDs.
        step_node_by_original_id: Mapping of source step IDs to compiled node IDs.
        node_type_by_id: Mapping of compiled node IDs to their types.

    Returns:
        The ID of the activity node to attach to, or None if no valid attachment found.
    """
    def as_activity(node_id: str | None) -> str | None:
        if node_id and node_type_by_id.get(node_id) in ACTIVITY_NODE_TYPES:
            return node_id
        return None

    direct = as_activity(step_node_by_original_id.get(exception.attached_to_step_id or ""))
    if direct is not None:
        return direct
    for edge in process.flow_edges:
        if edge.kind == "sequence" and edge.target_id == exception.id:
            candidate = as_activity(registry.compiled_for(edge.source_id))
            if candidate is not None:
                return candidate
    return None


def _exception_rejoin_node(
    exception: ProcessExceptionPath,
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    *,
    step_by_id: dict[str, ProcessStep],
    actor_lane_map: dict[str, str],
    actors: list[ProcessActor],
    nodes: list[BPMNFlowNode],
    used_ids: set[str],
    end_id: str,
    exception_source_ref: str,
) -> str | None:
    """Find or create the node where an exception handler rejoins the main flow.
    
    Args:
        exception (ProcessExceptionPath): Untrusted exception path defining the handler.
        process (ProcessUnderstanding): Untrusted process definition containing sequence edges.
        registry (FlowRegistry): Registry used to resolve and record compiled node IDs.
        step_by_id (dict[str, ProcessStep]): Mapping of step IDs to process steps.
        actor_lane_map (dict[str, str]): Mapping of actor IDs to lane IDs.
        actors (list[ProcessActor]): Process actors used to assign recovery-task ownership and lanes.
        nodes (list[BPMNFlowNode]): Mutable node collection to which created recovery tasks are appended.
        used_ids (set[str]): Mutable set of allocated XML identifiers.
        end_id (str): ID used as the recovery task's destination when no outgoing sequence edge exists.
        exception_source_ref (str): Source reference attached to created recovery tasks for traceability.
    
    Returns:
        str | None: The compiled rejoin node ID, or `None` when the exception has no resolvable
        sequence rejoin target.
    
    Side effects:
        May append a recovery task to `nodes`, allocate an identifier in `used_ids`, and update
        `registry` with the recovery-step mapping and an end-flow connection.
    """
    for edge in process.flow_edges:
        if edge.kind != "sequence" or edge.source_id != exception.id:
            continue
        compiled = registry.compiled_for(edge.target_id)
        if compiled is not None:
            return compiled
        recovery_step = step_by_id.get(edge.target_id)
        if recovery_step is not None:
            recovery = BPMNFlowNode(
                id=xml_id(recovery_step.id or "RecoveryTask", "Task", used_ids),
                type=_task_type(recovery_step),
                name=recovery_step.label,
                laneId=lane_for_step(recovery_step, actors, actor_lane_map),
                owner=actor_label(actors, recovery_step.actor_ids),
                sourceRefs=[source_ref_id("steps", recovery_step.id), exception_source_ref],
            )
            nodes.append(recovery)
            registry.map(recovery_step.id, recovery.id)
            if not any(
                other.kind == "sequence" and other.source_id == recovery_step.id
                for other in process.flow_edges
            ):
                registry.add(recovery.id, end_id)
            return recovery.id
    return None


_INTERRUPTING_ONLY_EXCEPTION_KINDS = frozenset({"error", "cancel"})


def _exception_event_definition(
    exception: ProcessExceptionPath,
) -> tuple[Literal["timer", "message", "error", "conditional", "escalation", "signal", "cancel"], bool]:
    """Resolve the boundary event definition and interrupting behavior for an exception path.
    
    Args:
        exception (ProcessExceptionPath): Untrusted exception-path data used to select
            the event type and interrupting behavior.
    
    Returns:
        tuple: The event definition type and whether the boundary event is interrupting.
            Explicit interrupting-only kinds and inferred error events are always
            interrupting.
    
    """
    if exception.kind != "auto":
        forced = exception.kind in _INTERRUPTING_ONLY_EXCEPTION_KINDS
        return exception.kind, True if forced else exception.interrupting

    text = f"{exception.trigger or ''} {exception.label or ''}"
    if _matches_word(text, ("timer", "timeout", "scadenza", "scaduto", "ritardo", "termine", "giorni", "ore")):
        return "timer", exception.interrupting
    if _matches_word(text, ("messaggio", "risposta", "notifica", "comunicazione", "riscontro")):
        return "message", exception.interrupting
    if exception.interrupting or _matches_word(text, ("errore", "guasto", "eccezione", "fault", "blocco", "anomalia")):
        return "error", True
    return "conditional", exception.interrupting


def _matches_word(text: str, words: tuple[str, ...]) -> bool:
    """Check if any word from a tuple appears as a whole word in the text.

    Args:
        text: The text to search in.
        words: A tuple of words to search for.

    Returns:
        True if any word is found as a complete word in the text, False otherwise.
    """
    lowered = text.casefold()
    return any(re.search(rf"\b{re.escape(word)}", lowered) for word in words)


def _normalize_event_gateways(
    nodes: list[BPMNFlowNode],
    registry: FlowRegistry,
    used_ids: set[str],
    warnings: list[str],
) -> None:
    """Every outgoing branch of an event-based gateway must begin with an element
    that waits for a trigger (OMG BPMN 2.0, 10.5.5). Splice a synthetic catch
    event onto any branch that currently jumps straight to an activity, gateway
    or end event; the branch label moves onto the catch event.
    """
    node_by_id = {node.id: node for node in nodes}
    for gateway in [node for node in nodes if node.type == "eventBasedGateway"]:
        insert_at = nodes.index(gateway) + 1
        for flow in [f for f in registry.flows if f.sourceRef == gateway.id]:
            target = node_by_id.get(flow.targetRef)
            if target is None or target.type in {"intermediateCatchEvent", "receiveTask"}:
                continue
            label = flow.name
            definition = _branch_catch_event_definition(f"{label or ''} {target.name}")
            condition_expression = (label or "").strip() or None
            if definition == "conditional" and condition_expression is None:
                warnings.append(
                    f"Ramo del gateway a eventi '{gateway.name}' verso '{target.name}' "
                    "senza trigger esplicito: catch event condizionale non generato."
                )
                continue
            catch = BPMNFlowNode(
                id=xml_id(f"{gateway.id}_{target.id}", "CatchEvent", used_ids),
                type="intermediateCatchEvent",
                name=label or f"Attesa: {target.name}",
                eventDefinition=definition,
                eventConditionExpression=(
                    condition_expression if definition == "conditional" else None
                ),
                laneId=gateway.laneId or target.laneId,
            )
            # Keep the synthetic catch next to its gateway so the serializer and
            # layout column-rank it on the branch, not past the end event.
            nodes.insert(insert_at, catch)
            insert_at += 1
            node_by_id[catch.id] = catch
            registry.insert_node(gateway.id, target.id, catch.id)
            flow.name = None


def _add_synchronizing_joins(
    nodes: list[BPMNFlowNode],
    registry: FlowRegistry,
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    used_ids: set[str],
) -> None:
    """Close each parallel, inclusive or complex split with a join of its own type.

    The join goes in front of the first node where two or more of the split's
    branches meet; without it that node would run once per arriving token. A
    flow coming back from after the meeting point (a rework loop) is not a
    branch and stays where it is.
    """
    successors: dict[str, list[str]] = {}
    for flow in registry.flows:
        successors.setdefault(flow.sourceRef, []).append(flow.targetRef)

    def reachable(start: str, blocked: str | None = None) -> set[str]:
        seen, stack = set(), [start]
        while stack:
            node_id = stack.pop()
            if node_id in seen or node_id == blocked:
                continue
            seen.add(node_id)
            stack.extend(successors.get(node_id, []))
        return seen

    for split in list(gateway_by_decision_id.values()):
        if split.type not in _SYNCHRONIZING_GATEWAYS or registry.outgoing_count(split.id) < 2:
            continue
        order = _breadth_first(split.id, successors)
        for meeting in order[1:]:
            region = reachable(split.id, blocked=meeting)
            downstream = reachable(meeting)
            branches = [
                flow for flow in registry.flows
                if flow.targetRef == meeting and flow.sourceRef in region and flow.sourceRef not in downstream
            ]
            if len(branches) < 2:
                continue
            join = BPMNFlowNode(
                id=xml_id(f"{split.id}_join", "Gateway", used_ids),
                type=split.type,
                name="",
                laneId=next((n.laneId for n in nodes if n.id == meeting), split.laneId),
                activationCondition=split.activationCondition,
            )
            nodes.insert(next(i for i, n in enumerate(nodes) if n.id == meeting), join)
            for flow in branches:
                registry.retarget(flow, join.id)
            registry.add(join.id, meeting)
            break


def _add_exclusive_merges(
    nodes: list[BPMNFlowNode],
    registry: FlowRegistry,
    used_ids: set[str],
) -> None:
    """Put an exclusive merge in front of every non-gateway node with several entries.

    An activity, event or end event reached by more than one sequence flow
    merges them implicitly: legal BPMN, but the reader has to infer it and the
    split it closes stays open on the diagram. The merge gateway makes it
    explicit and leaves the node with one entry. Synchronizing joins are
    already in place, so what still meets here is exclusive (alternative
    branches, rework loops, exception handlers rejoining). A catch event behind
    an event-based gateway keeps its entries: nothing may sit between the two.
    Merges go at the end of `nodes`: order carries no meaning in BPMN, and the
    plan's own elements stay ahead of the ones the compiler adds.
    """
    type_by_id = {node.id: node.type for node in nodes}
    for node in list(nodes):
        if node.type.endswith("Gateway") or node.type in {"startEvent", "boundaryEvent"}:
            continue
        entries = [flow for flow in registry.flows if flow.targetRef == node.id]
        if len(entries) < 2:
            continue
        if any(type_by_id.get(flow.sourceRef) == "eventBasedGateway" for flow in entries):
            continue
        merge = BPMNFlowNode(
            id=xml_id(f"{node.id}_merge", "Gateway", used_ids),
            type="exclusiveGateway",
            name="",
            laneId=node.laneId,
        )
        nodes.append(merge)
        for flow in entries:
            registry.retarget(flow, merge.id)
        registry.add(merge.id, node.id)


def _breadth_first(start: str, successors: dict[str, list[str]]) -> list[str]:
    """Nodes reachable from `start`, nearest first."""
    order, seen, queue = [], {start}, deque([start])
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in successors.get(node_id, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return order


def _assign_gateway_defaults(
    nodes: list[BPMNFlowNode],
    flows: list,
    warnings: list[str],
    *,
    declared_default_ids: frozenset[str] | set[str] = frozenset(),
) -> None:
    """Assign each data-based gateway its default flow.

    The branch of an outcome the plan declares as default wins, and loses any
    condition a flow edge gave it (in BPMN the default flow has none).
    Otherwise a gateway with exactly one bare branch marks it as the default.

    Args:
        nodes: List of BPMN flow nodes including gateways.
        flows: List of sequence flows.
        warnings: List to append warning messages to.
        declared_default_ids: Flows of outcomes the plan marks as default.
    """
    outgoing: dict[str, list] = {}
    for flow in flows:
        outgoing.setdefault(flow.sourceRef, []).append(flow)

    for node in nodes:
        if node.type not in _DATA_BASED_GATEWAYS:
            continue
        branches = outgoing.get(node.id, [])
        if len(branches) < 2:
            continue
        declared = next((flow for flow in branches if flow.id in declared_default_ids), None)
        if declared is not None:
            declared.conditionExpression = None
            node.defaultFlowId = declared.id
            continue
        unconditioned = [flow for flow in branches if not flow.conditionExpression]
        if len(unconditioned) == 1:
            node.defaultFlowId = unconditioned[0].id
        elif len(unconditioned) > 1:
            warnings.append(
                f"Gateway '{node.name}' con piu' di un ramo senza condizione: "
                "definire le condizioni o un ramo di default."
            )


def _label_decision_outcomes(
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    gateway_by_decision_id: dict[str, BPMNFlowNode],
) -> list[BPMNSequenceFlow]:
    """Carry each decision outcome onto the gateway branch it selects.

    The branch takes the outcome's label and, unless the outcome is the default
    one, its condition: in BPMN the default flow is the one without a condition.
    Only flows already drawn are touched; an outcome never becomes a new branch here.
    Parallel branches take the label only: all of them always run. Event-based
    gateways are left alone: the event that arrives first picks the branch, and
    only a flow edge naming that event says what its catch event waits for.

    Returns:
        The branches of the outcomes the plan marks as default.
    """
    defaults: list[BPMNSequenceFlow] = []
    for decision in process.decisions:
        gateway = gateway_by_decision_id.get(decision.id)
        if gateway is None or gateway.type == "eventBasedGateway":
            continue
        for outcome in decision.outcome_details:
            target = registry.compiled_for(outcome.target_path_id or outcome.target_ref or "")
            if not target or (gateway.id, target) not in registry.seen_pairs:
                continue
            flow = registry.add(gateway.id, target, name=outcome.label)
            if flow is None:
                continue
            if gateway.type == "parallelGateway":
                continue  # every branch runs: no default, no condition
            if outcome.is_default:
                defaults.append(flow)
            elif outcome.condition and not flow.conditionExpression:
                flow.conditionExpression = outcome.condition
    return defaults


def _complete_flow_graph(
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    nodes: list[BPMNFlowNode],
    warnings: list[str],
) -> None:
    """Add remaining flow_edges transitions that don't corrupt control flow.

    Only adds edges when safe: never into a start event, never a second exit from
    an activity, never an uncontrolled merge.

    Args:
        process: The ProcessUnderstanding containing flow_edges.
        registry: FlowRegistry for adding sequence flows.
        nodes: List of BPMN flow nodes for type checking.
        warnings: List to append warning messages to.
    """
    node_type_by_id = {node.id: node.type for node in nodes}
    mergeable = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "complexGateway", "endEvent"}

    for edge in process.flow_edges:
        if edge.kind != "sequence":
            continue
        source = registry.compiled_for(edge.source_id)
        target = registry.compiled_for(edge.target_id)
        if not source or not target or source == target or (source, target) in registry.seen_pairs:
            continue

        source_type = node_type_by_id.get(source, "")
        target_type = node_type_by_id.get(target, "")
        if target_type == "startEvent":
            warnings.append(
                f"Transizione '{edge.label or edge.id}' ignorata: un evento iniziale non "
                "puo avere frecce in ingresso."
            )
            continue

        target_ok = target_type in mergeable or registry.incoming_count(target) <= 1
        source_ok = source_type.endswith("Gateway") or registry.outgoing_count(source) == 0
        if source_ok and target_ok:
            registry.add(source, target)
        else:
            warnings.append(
                f"Transizione '{edge.label or edge.id}' non modellata: creerebbe un ramo "
                "implicito; serve un gateway esplicito."
            )


def _semantic_warnings(
    process: ProcessUnderstanding,
    lanes: list[BPMNLane],
    *,
    collaboration_built: bool = False,
) -> list[str]:
    """Generate semantic warnings about the compiled BPMN model.

    Args:
        process: The source ProcessUnderstanding.
        lanes: List of compiled BPMN lanes.
        collaboration_built: Whether a collaboration structure was built.

    Returns:
        A list of warning messages about semantic concerns.
    """
    warnings = list(process.assumptions)
    external_actor_names = [actor.label for actor in process.actors if actor.kind == "external_party"]
    if external_actor_names and not collaboration_built:
        warnings.append(
            "Partecipanti esterni modellati come lane nella prima slice: "
            + ", ".join(external_actor_names)
            + ". Da trasformare in pool/message flow nella fase successiva."
        )
    if process.unknowns:
        warnings.extend(item.question for item in process.unknowns)
    if process.decisions and not any(path.sequence for path in process.alternative_paths):
        warnings.append("Decisioni presenti, ma i percorsi alternativi non sono ancora completamente confermati.")
    if process.handoffs and len(lanes) < 2:
        warnings.append("Handoff presenti, ma le lane rilevate non bastano a rappresentare il passaggio di responsabilita.")
    if process.loops:
        warnings.append("Loop presenti: verificare condizioni di rientro e uscita nel canvas.")
    pool_candidates = [item.actor_id for item in process.actor_relationships if item.bpmn_pool_candidate]
    if pool_candidates and not collaboration_built:
        warnings.append("Candidati a pool/message flow esterni: " + ", ".join(pool_candidates[:8]))
    if not lanes:
        warnings.append("Nessun ruolo/lane rilevato dalle note.")
    return warnings


def _start_name(process: ProcessUnderstanding) -> str:
    """Determine the name for the start event.

    Args:
        process: The ProcessUnderstanding model.

    Returns:
        The name for the start event.
    """
    if process.boundaries and process.boundaries.start_event:
        return process.boundaries.start_event
    event = next((item for item in process.events if item.type == "start"), None)
    return event.label if event else "Start"


_START_TIMER_WORDS = (
    "ogni", "giornaliero", "giornaliera", "settimanale", "mensile", "trimestrale", "annuale",
    "calendario", "fine mese", "every", "daily", "weekly", "monthly",
)
_START_MESSAGE_WORDS = (
    "messaggio", "email", "e-mail", "mail", "pec", "ricevuta", "ricevuto", "ricezione",
    "riceve", "arriva", "arrivo", "notifica", "comunicazione", "message", "received",
)


def _start_event_definition(process: ProcessUnderstanding) -> Literal["timer", "message", "signal"] | None:
    """Infer the BPMN trigger of the start event from what the plan says starts it.

    A plain (none) start when the trigger names no message, timer or signal:
    a guessed trigger would assert something the sources do not say.
    """
    boundaries = process.boundaries
    texts = [boundaries.trigger, boundaries.start_event] if boundaries else []
    texts += [event.label for event in process.events if event.type == "start"]
    text = " ".join(item for item in texts if item)
    if not text:
        return None
    if _matches_word(text, _START_TIMER_WORDS):
        return "timer"
    if _matches_word(text, _SIGNAL_WORDS):
        return "signal"
    if _matches_word(text, _START_MESSAGE_WORDS):
        return "message"
    return None


def _end_name(process: ProcessUnderstanding) -> str:
    """Determine the name for the primary end event.

    Args:
        process: The ProcessUnderstanding model.

    Returns:
        The name for the end event.
    """
    if process.boundaries and process.boundaries.success_end:
        return process.boundaries.success_end
    event = next((item for item in process.events if item.type == "end"), None)
    return event.label if event else "End"


def _norm_end_key(value: str | None) -> str:
    """Normalize an end event key for comparison.

    Args:
        value: The raw key string.

    Returns:
        A normalized, lowercase, whitespace-collapsed key.
    """
    return " ".join((value or "").casefold().split())


def _terminating_end_keys(process: ProcessUnderstanding) -> set[str]:
    """Identify normalized keys for process boundaries that terminate all work.
    
    Args:
        process (ProcessUnderstanding): Process data, potentially originating from
            untrusted input.
    
    Returns:
        set[str]: Non-empty normalized keys of terminating boundaries, or an empty
            set when no boundaries are defined.
    """
    if not process.boundaries:
        return set()
    return {_norm_end_key(item) for item in process.boundaries.terminating_ends if item}


def _end_event_definition(
    keys: set[str], terminating: set[str]
) -> Literal["terminate"] | None:
    """A terminate end definition when any of the node's keys is a terminating end."""
    return "terminate" if keys & terminating else None


def _build_end_events(
    process: ProcessUnderstanding,
    used_ids: set[str],
) -> tuple[BPMNFlowNode, dict[str, BPMNFlowNode]]:
    """Create end-event nodes for the process's distinct outcomes.
    
    Args:
        process: Untrusted process definition containing declared events and boundary outcomes.
        used_ids: Set of allocated XML identifiers, updated with identifiers reserved for
            newly created end events.
    
    Returns:
        A tuple containing the primary end event and a mapping from event identifiers or
        normalized outcome labels to their corresponding end events. The primary event
        uses the configured success outcome when available; otherwise, it is the first
        created end event. If no outcomes are declared, a default end event is returned.
    """
    by_key: dict[str, BPMNFlowNode] = {}
    created: list[BPMNFlowNode] = []
    terminating = _terminating_end_keys(process)

    for event in process.events:
        if event.type != "end":
            continue
        terminate = _end_event_definition({_norm_end_key(event.id), _norm_end_key(event.label)}, terminating)
        node = BPMNFlowNode(
            id=xml_id(event.id or "EndEvent", "EndEvent", used_ids),
            type="endEvent",
            name=event.label or "Fine",
            **(
                {"eventDefinition": terminate}
                if terminate
                else _event_definition_fields(event, "endEvent", event.definition)
            ),
            sourceRefs=[source_ref_id("events", event.id)],
        )
        created.append(node)
        by_key[event.id] = node
        by_key.setdefault(_norm_end_key(event.label), node)

    if process.boundaries:
        # success_end first so the configured happy-path end is created and,
        # below, selected as the primary plain end (never a terminate end).
        extra_ends = [
            ("boundaries", label, name)
            for label, name in (
                *([(process.boundaries.success_end, "Fine")] if process.boundaries.success_end else []),
                *((label, "Fine con esito negativo") for label in process.boundaries.failure_ends),
                *((label, "Fine con interruzione") for label in process.boundaries.terminating_ends),
            )
        ]
        for field, label, default_name in extra_ends:
            if _norm_end_key(label) in by_key:
                continue
            node = BPMNFlowNode(
                id=xml_id(label or "EndEvent", "EndEvent", used_ids),
                type="endEvent",
                name=label or default_name,
                eventDefinition=_end_event_definition({_norm_end_key(label)}, terminating),
                sourceRefs=[source_ref_id(field, label)],
            )
            created.append(node)
            by_key[_norm_end_key(label)] = node

    if not created:
        default = BPMNFlowNode(
            id=xml_id("EndEvent_1", "EndEvent", used_ids), type="endEvent", name=_end_name(process)
        )
        return default, {"__default__": default}

    primary: BPMNFlowNode | None = None
    if process.boundaries and process.boundaries.success_end:
        primary = by_key.get(_norm_end_key(process.boundaries.success_end))
    # The happy-path end must consume its own token, never abort the process. If
    # the configured success_end resolves (by label or event id) to a terminate
    # end, or no plain end exists at all, mint a distinct plain success end.
    if primary is None or primary.eventDefinition == "terminate":
        primary = next((node for node in created if node.eventDefinition != "terminate"), None)
    if primary is None:
        success_name = (
            process.boundaries.success_end
            if process.boundaries and process.boundaries.success_end
            else _end_name(process)
        )
        primary = BPMNFlowNode(
            id=xml_id("EndEvent_Success", "EndEvent", used_ids), type="endEvent", name=success_name
        )
        created.append(primary)
        by_key.setdefault(_norm_end_key(success_name), primary)
    return primary, by_key


def _end_for(
    target: str | None,
    end_node_by_key: dict[str, BPMNFlowNode],
    fallback: BPMNFlowNode,
) -> BPMNFlowNode:
    """Resolve a target string to an end event node.

    Args:
        target: The target end event ID or label to look up.
        end_node_by_key: Dictionary of end events keyed by ID or normalized label.
        fallback: The default end event to return if target is not found.

    Returns:
        The matching end event node, or the fallback if not found.
    """
    if not target:
        return fallback
    return (
        end_node_by_key.get(target)
        or end_node_by_key.get(_norm_end_key(target))
        or fallback
    )


def _outcome_name_for_path(decision: ProcessDecision, path) -> str | None:
    """Find the outcome label for a decision that leads to a specific path.

    Args:
        decision: The ProcessDecision with outcome_details.
        path: The alternative path to find the outcome for.

    Returns:
        The outcome label or condition, or the path's own label as fallback.
    """
    for outcome in decision.outcome_details:
        if outcome.target_path_id == path.id:
            return outcome.label or outcome.condition
    return path.trigger_or_condition or path.label
