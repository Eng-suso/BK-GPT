"""Compile a `ProcessUnderstanding` into a `BPMNSemanticModel`.

Deterministic: the LLM's semantic judgement is already baked into the
`ProcessUnderstanding`; this module only turns that structure into well-formed
BPMN (chain, gateways, branches, loops, intermediate events, boundary events,
collaboration) and records where every source item landed.
"""

from __future__ import annotations

import re
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
    CollaborationLayer,
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
    BPMNFlowNode,
    BPMNLane,
    BPMNSemanticModel,
)
from backend.process_understanding import (
    ProcessActor,
    ProcessDecision,
    ProcessEvent,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
)

_INTERMEDIATE_EVENT_DEFINITION: dict[str, Literal["timer", "message"]] = {
    "timer": "timer",
    "message": "message",
}

_GATEWAY_BPMN_TYPE: dict[str, str] = {
    "exclusive": "exclusiveGateway",
    "inclusive": "inclusiveGateway",
    "event_based": "eventBasedGateway",
}

# Gateways whose outgoing flows carry data-based condition expressions. Parallel
# and event-based gateways never do (they fork on tokens / on which event fires).
_DATA_BASED_GATEWAYS = frozenset({"exclusiveGateway", "inclusiveGateway"})


def _gateway_bpmn_type(decision: ProcessDecision) -> str:
    """Map a process decision's gateway type to its BPMN gateway type.
    
    Parameters:
    	decision (ProcessDecision): The decision whose gateway type is mapped.
    
    Returns:
    	str: The corresponding BPMN gateway type, defaulting to ``exclusiveGateway``.
    """
    return _GATEWAY_BPMN_TYPE.get(decision.gateway_type, "exclusiveGateway")


def _branch_catch_event_definition(text: str) -> Literal["timer", "message", "signal", "conditional"]:
    """Infer the catch-event trigger for an event-based gateway branch."""
    if _matches_word(text, ("timer", "timeout", "scadenza", "scaduto", "ritardo", "termine", "giorni", "ore")):
        return "timer"
    if _matches_word(text, ("segnale", "signal", "broadcast", "evento di sistema")):
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
    Compile a process understanding into a BPMN semantic model.
    
    Parameters:
    	process_id (str): Identifier used to create the BPMN process ID.
    	process_name (str): Name assigned to the BPMN process.
    	process (ProcessUnderstanding): Process definition to compile.
    
    Returns:
    	BPMNSemanticModel: The compiled BPMN semantic model.
    
    Raises:
    	ValueError: If compilation would result in information loss.
    """
    used_ids: set[str] = set()
    safe_process_id = xml_id(process_id, "Process", used_ids)
    collaboration = build_collaboration_layer(process, safe_process_id, used_ids)
    lanes = collaboration.lanes
    actor_lane_map = collaboration.lane_by_actor_id
    step_by_id = {step.id: step for step in process.steps}
    ordered_chain = _ordered_chain_items(process, step_by_id)

    nodes: list[BPMNFlowNode] = [
        BPMNFlowNode(id=xml_id("StartEvent_1", "StartEvent", used_ids), type="startEvent", name=_start_name(process)),
    ]
    warnings = _semantic_warnings(
        process, lanes, collaboration_built=collaboration.collaboration_id is not None
    )
    warnings.extend(collaboration.warnings)
    registry = FlowRegistry(
        used_ids=used_ids,
        edges_by_original=sequence_flow_edges_by_endpoint(process),
    )
    for event in process.events:
        if event.type == "start":
            registry.map(event.id, nodes[0].id)

    main_chain: list[str] = [nodes[0].id]
    step_node_by_original_id: dict[str, str] = {}
    gateway_by_decision_id: dict[str, BPMNFlowNode] = {}
    gateway_by_step_id: dict[str, BPMNFlowNode] = {}
    decision_by_anchor_step_id, decision_anchor_warnings = _decision_anchor_map(process, ordered_chain)
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
            name=step.label,
            laneId=lane_id,
            owner=actor_label(process.actors, step.actor_ids),
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

    registry.gateway_ids = {node.id for node in nodes if node.type in _DATA_BASED_GATEWAYS}
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
    _normalize_event_gateways(nodes, registry, used_ids)
    flows = registry.flows
    _assign_gateway_defaults(nodes, flows, warnings)
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
        associations=data_flow.associations,
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
    """Map a ProcessStep type to the corresponding BPMN task type.

    Args:
        step: The ProcessStep to classify.

    Returns:
        A BPMN task type string (e.g., "userTask", "serviceTask").
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
    }.get(step.type, "userTask")


def _ordered_chain_items(
    process: ProcessUnderstanding,
    step_by_id: dict[str, ProcessStep],
) -> list[ProcessStep | ProcessEvent]:
    """Ordered flow nodes for the main path: steps plus the timer / message
    intermediate events that sit between them (placed from main_success_path /
    sequence, or spliced after the flow_edges predecessor)."""
    flow_event_by_id = {
        event.id: event
        for event in process.events
        if event.id and event.type in _INTERMEDIATE_EVENT_DEFINITION
    }
    chain: list[ProcessStep | ProcessEvent] = []
    for item_id in process.main_success_path or process.sequence:
        if item_id in step_by_id:
            chain.append(step_by_id[item_id])
        elif item_id in flow_event_by_id:
            chain.append(flow_event_by_id[item_id])
    if not chain:
        chain = list(process.steps)

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
    """
    Create and register a BPMN gateway for the decision anchored to a main-chain step.
    """
    decision = decision_by_anchor_step_id.get(anchor_id)
    if decision is None:
        return
    gateway = BPMNFlowNode(
        id=xml_id(decision.id, "Gateway", used_ids),
        type=_gateway_bpmn_type(decision),
        name=decision.label,
        laneId=lane_id,
        documentation=decision_documentation(decision),
        sourceRefs=[source_ref_id("decisions", decision.id)],
    )
    nodes.append(gateway)
    main_chain.append(gateway.id)
    registry.map(decision.id, gateway.id)
    gateway_by_decision_id[decision.id] = gateway
    gateway_by_step_id[anchor_id] = gateway


def _event_node(event: ProcessEvent, used_ids: set[str]) -> BPMNFlowNode:
    """Create a BPMN intermediate event node from a ProcessEvent.

    A throwing event (the process emits a message/signal) becomes an
    `intermediateThrowEvent`; everything else waits and becomes an
    `intermediateCatchEvent`.
    """
    node_type = "intermediateThrowEvent" if event.direction == "throw" else "intermediateCatchEvent"
    return BPMNFlowNode(
        id=xml_id(event.id or "IntermediateEvent", "IntermediateEvent", used_ids),
        type=node_type,
        name=event.label,
        eventDefinition=_INTERMEDIATE_EVENT_DEFINITION.get(event.type),
        documentation=json_documentation(
            "event",
            {"type": event.type, "timing": event.timing, "source_evidence": event.source_evidence},
        ),
        sourceRefs=[source_ref_id("events", event.id)],
    )


def _decision_anchor_map(
    process: ProcessUnderstanding,
    ordered_chain: list[ProcessStep | ProcessEvent],
) -> tuple[dict[str, ProcessDecision], list[str]]:
    ordered_step_ids = [item.id for item in ordered_chain if item.id]
    decision_by_anchor: dict[str, ProcessDecision] = {}
    warnings: list[str] = []
    unassigned = list(process.decisions)

    for path in process.alternative_paths:
        decision = _decision_for_path(path, unassigned)
        if decision is None:
            continue
        anchor_step_id = _anchor_step_for_decision(process, decision, ordered_step_ids)
        if anchor_step_id is None:
            warnings.append(
                f"Decisione '{decision.label}' senza flow edge di ingresso da uno step del percorso principale."
            )
            continue
        if anchor_step_id in decision_by_anchor:
            warnings.append(
                f"Piu' decisioni candidate sullo stesso step '{anchor_step_id}'; verificare il modello."
            )
            continue
        decision_by_anchor[anchor_step_id] = decision
        unassigned = [item for item in unassigned if item.id != decision.id]

    for decision in unassigned:
        anchor_step_id = _anchor_step_for_decision(process, decision, ordered_step_ids)
        if anchor_step_id and anchor_step_id not in decision_by_anchor:
            decision_by_anchor[anchor_step_id] = decision
        else:
            warnings.append(f"Decisione '{decision.label}' non mappabile: manca anchor esplicito in flow_edges.")

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
    """Find the anchor step that precedes a decision in the main path.

    Args:
        process: The ProcessUnderstanding model.
        decision: The ProcessDecision to find an anchor for.
        ordered_step_ids: List of step IDs in the main path.

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
    actors: list[ProcessActor],
    actor_lane_map: dict[str, str],
    warnings: list[str],
) -> None:
    unassigned_paths = list(process.alternative_paths)
    gateways = list(gateway_by_decision_id.values())

    for decision in process.decisions:
        gateway = gateway_by_decision_id.get(decision.id)
        if gateway is None:
            continue

        path = _take_alternative_path_for_decision(decision, unassigned_paths)
        if path is None:
            warnings.append(f"Gateway '{decision.label}' senza alternative path esplicito collegato.")
            continue
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
                name=source_step.label,
                laneId=lane_id,
                owner=actor_label(actors, source_step.actor_ids),
            )
            nodes.append(branch_node)
            registry.map(source_step.id, branch_node.id)
            registry.add(
                previous_id,
                branch_node.id,
                name=outcome_name if previous_id == gateway.id else None,
            )
            previous_id = branch_node.id

        if path.rejoins_at and path.rejoins_at in step_node_by_original_id:
            registry.add(previous_id, step_node_by_original_id[path.rejoins_at], name=path.trigger_or_condition)
        elif path.ends_at and path.ends_at in step_node_by_original_id:
            registry.add(previous_id, step_node_by_original_id[path.ends_at], name=path.trigger_or_condition)
        else:
            end_target = _resolve_alt_path_end(
                path, outcome_name, gateway.laneId, end_node_by_key, primary_end, nodes, used_ids
            )
            registry.add(previous_id, end_target, name=path.trigger_or_condition)

        if not path.is_confirmed:
            warnings.append(f"Alternative path '{path.label}' non confermato.")

    if unassigned_paths and not gateways:
        warnings.append("Alternative path presenti, ma nessun gateway decisionale e' stato generato.")
    elif unassigned_paths:
        for path in unassigned_paths:
            warnings.append(f"Alternative path '{path.label}' non collegato a un outcome decisionale esplicito.")


def _resolve_alt_path_end(
    path,
    outcome_name: str | None,
    lane_id: str | None,
    end_node_by_key: dict[str, BPMNFlowNode],
    primary_end: BPMNFlowNode,
    nodes: list[BPMNFlowNode],
    used_ids: set[str],
) -> str:
    """Route an alternative path's terminal edge to an existing end event when
    its `ends_at` names one, otherwise mint a distinct end for that outcome."""
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


def _take_alternative_path_for_decision(decision, paths: list):
    if not paths:
        return None
    for index, path in enumerate(paths):
        if _path_matches_decision(decision, path):
            return paths.pop(index)
    return None


def _path_matches_decision(decision, path) -> bool:
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
    node_by_id = {node.id: node for node in nodes}
    for loop in process.loops:
        repeated = [step_id for step_id in loop.repeated_steps if step_id in step_node_by_original_id]
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
    node_type_by_id = {node.id: node.type for node in nodes}
    node_lane_by_id = {node.id: node.laneId for node in nodes}

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


def _exception_event_definition(
    exception: ProcessExceptionPath,
) -> tuple[Literal["timer", "message", "error", "conditional"], bool]:
    """Resolve (eventDefinition, interrupting) for an exception boundary event.

    Error boundary events must be interrupting per BPMN 2.0; when the process
    asked for non-interrupting handling of an otherwise-unclassified trigger we
    fall back to a conditional boundary event, which may be non-interrupting.
    """
    text = f"{exception.trigger or ''} {exception.label or ''}"
    if _matches_word(text, ("timer", "timeout", "scadenza", "scaduto", "ritardo", "termine", "giorni", "ore")):
        return "timer", exception.interrupting
    if _matches_word(text, ("messaggio", "risposta", "notifica", "comunicazione", "riscontro")):
        return "message", exception.interrupting
    if exception.interrupting or _matches_word(text, ("errore", "guasto", "eccezione", "fault", "blocco", "anomalia")):
        return "error", True
    return "conditional", exception.interrupting


def _matches_word(text: str, words: tuple[str, ...]) -> bool:
    """
    Determine whether text contains a case-insensitive word-prefix match.
    
    Parameters:
        text (str): Text to search.
        words (tuple[str, ...]): Word prefixes to match.
    
    Returns:
        bool: `true` if text contains a matching word prefix, `false` otherwise.
    """
    lowered = text.casefold()
    return any(re.search(rf"\b{re.escape(word)}", lowered) for word in words)


def _normalize_event_gateways(
    nodes: list[BPMNFlowNode], registry: FlowRegistry, used_ids: set[str]
) -> None:
    """
    Ensure every event-based gateway branch begins with an intermediate catch event.
    
    Branches that already begin with a catch event or receive task remain unchanged. Synthetic catch events inherit the branch label and relevant lane and source references.
    """
    node_by_id = {node.id: node for node in nodes}
    for gateway in list(nodes):
        if gateway.type != "eventBasedGateway":
            continue
        for flow in [f for f in registry.flows if f.sourceRef == gateway.id]:
            target = node_by_id.get(flow.targetRef)
            if target is None or target.type in {"intermediateCatchEvent", "receiveTask"}:
                continue
            label = flow.name
            catch = BPMNFlowNode(
                id=xml_id(f"{gateway.id}_{target.id}", "CatchEvent", used_ids),
                type="intermediateCatchEvent",
                name=label or f"Attesa: {target.name}",
                eventDefinition=_branch_catch_event_definition(f"{label or ''} {target.name}"),
                laneId=gateway.laneId or target.laneId,
                sourceRefs=list(gateway.sourceRefs),
            )
            nodes.append(catch)
            node_by_id[catch.id] = catch
            registry.insert_node(gateway.id, target.id, catch.id)
            flow.name = None


def _assign_gateway_defaults(
    nodes: list[BPMNFlowNode],
    flows: list,
    warnings: list[str],
) -> None:
    """
    Assigns the sole unconditioned outgoing flow as the default for exclusive and inclusive gateways.
    
    Adds a warning when multiple outgoing flows lack conditions.
    """
    outgoing: dict[str, list] = {}
    for flow in flows:
        outgoing.setdefault(flow.sourceRef, []).append(flow)

    for node in nodes:
        if node.type not in {"exclusiveGateway", "inclusiveGateway"}:
            continue
        branches = outgoing.get(node.id, [])
        if len(branches) < 2:
            continue
        unconditioned = [flow for flow in branches if not flow.conditionExpression]
        if len(unconditioned) == 1:
            node.defaultFlowId = unconditioned[0].id
        elif len(unconditioned) > 1:
            warnings.append(
                f"Gateway '{node.name}' con piu' di un ramo senza condizione: "
                "definire le condizioni o un ramo di default."
            )


def _complete_flow_graph(
    process: ProcessUnderstanding,
    registry: FlowRegistry,
    nodes: list[BPMNFlowNode],
    warnings: list[str],
) -> None:
    """Add flow_edges transitions the skeleton generators missed, only when the
    addition cannot corrupt control flow (never into a start event, never a
    second exit from an activity, never an uncontrolled merge)."""
    node_type_by_id = {node.id: node.type for node in nodes}
    mergeable = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "endEvent"}

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


def _build_end_events(
    process: ProcessUnderstanding,
    used_ids: set[str],
) -> tuple[BPMNFlowNode, dict[str, BPMNFlowNode]]:
    """One end event per distinct outcome: the `type=="end"` events plus any
    `boundaries.failure_ends` not already covered. Keyed by event id and by
    normalised label so alternative paths can route to the right one."""
    by_key: dict[str, BPMNFlowNode] = {}
    created: list[BPMNFlowNode] = []

    for event in process.events:
        if event.type != "end":
            continue
        node = BPMNFlowNode(
            id=xml_id(event.id or "EndEvent", "EndEvent", used_ids),
            type="endEvent",
            name=event.label or "Fine",
            sourceRefs=[source_ref_id("events", event.id)],
        )
        created.append(node)
        by_key[event.id] = node
        by_key.setdefault(_norm_end_key(event.label), node)

    if process.boundaries:
        for label in process.boundaries.failure_ends:
            if _norm_end_key(label) in by_key:
                continue
            node = BPMNFlowNode(
                id=xml_id(label or "EndEvent", "EndEvent", used_ids),
                type="endEvent",
                name=label or "Fine con esito negativo",
                sourceRefs=[source_ref_id("boundaries", label)],
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
    return primary or created[0], by_key


def _end_for(
    target: str | None,
    end_node_by_key: dict[str, BPMNFlowNode],
    fallback: BPMNFlowNode,
) -> BPMNFlowNode:
    if not target:
        return fallback
    return (
        end_node_by_key.get(target)
        or end_node_by_key.get(_norm_end_key(target))
        or fallback
    )


def _outcome_name_for_path(decision: ProcessDecision, path) -> str | None:
    """
    Determine the label for a decision path.
    
    Parameters:
        decision (ProcessDecision): Decision containing outcome details.
        path: Decision path whose outcome label is resolved.
    
    Returns:
        str | None: The matching outcome label or condition, or the path trigger or label.
    """
    for outcome in decision.outcome_details:
        if outcome.target_path_id == path.id:
            return outcome.label or outcome.condition
    return path.trigger_or_condition or path.label

