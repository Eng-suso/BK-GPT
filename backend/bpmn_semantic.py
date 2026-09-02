from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from typing import Literal

from pydantic import BaseModel, Field

from backend.bpmn_topology import PoolTopology, ResolvedPool, resolve_pool_topology
from backend.process_understanding import (
    ProcessActor,
    ProcessDecision,
    ProcessEvent,
    ProcessExceptionPath,
    ProcessFlowEdge,
    ProcessStep,
    ProcessUnderstanding,
)


class BPMNFlowNode(BaseModel):
    id: str
    type: Literal[
        "startEvent",
        "endEvent",
        "task",
        "userTask",
        "serviceTask",
        "manualTask",
        "sendTask",
        "receiveTask",
        "businessRuleTask",
        "scriptTask",
        "exclusiveGateway",
        "parallelGateway",
        "intermediateCatchEvent",
        "boundaryEvent",
        "subProcess",
    ]
    name: str
    laneId: str | None = None
    owner: str | None = None
    eventDefinition: Literal["timer", "message", "conditional", "signal", "error"] | None = None
    attachedToRef: str | None = None
    cancelActivity: bool = True
    defaultFlowId: str | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNSequenceFlow(BaseModel):
    id: str
    sourceRef: str
    targetRef: str
    name: str | None = None
    conditionExpression: str | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNLane(BaseModel):
    id: str
    name: str
    flowNodeRefs: list[str] = Field(default_factory=list)
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNDataObject(BaseModel):
    id: str
    name: str
    kind: str = "data"
    sourceNodeRef: str | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNTextAnnotation(BaseModel):
    id: str
    text: str
    sourceNodeRef: str | None = None


class BPMNAssociation(BaseModel):
    id: str
    sourceRef: str
    targetRef: str


class BPMNParticipant(BaseModel):
    id: str
    name: str
    processRef: str | None = None
    isExternal: bool = False
    rendering: Literal["expanded", "black_box", "out_of_scope"] = "expanded"
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNMessageFlow(BaseModel):
    id: str
    sourceRef: str
    targetRef: str
    name: str | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


MappingStatus = Literal["direct", "encoded", "visual_annotation", "semantic_payload", "blocked"]


class ProcessUnderstandingRef(BaseModel):
    field: str
    id: str | None = None
    label: str | None = None


class TraceabilityLink(BaseModel):
    source: ProcessUnderstandingRef
    target_id: str
    target_type: str
    mapping_status: MappingStatus = "direct"
    rationale: str = ""


class CompilationCoverageReport(BaseModel):
    total_source_items: int
    represented_source_items: int
    losses: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    traceability: list[TraceabilityLink] = Field(default_factory=list)


class ParticipantSpec(BaseModel):
    id: str
    name: str
    kind: str
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)
    mapping_status: MappingStatus = "direct"


class LaneSpec(BaseModel):
    id: str
    name: str
    actor_id: str
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class ActivitySpec(BaseModel):
    id: str
    name: str
    type: str
    lane_id: str | None = None
    documentation: str = ""
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class GatewaySpec(BaseModel):
    id: str
    name: str
    type: Literal["exclusiveGateway", "parallelGateway", "inclusiveGateway"] = "exclusiveGateway"
    anchor_step_id: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    documentation: str = ""
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class EventSpec(BaseModel):
    id: str
    name: str
    type: str
    documentation: str = ""
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class FlowSpec(BaseModel):
    id: str
    source_ref: str
    target_ref: str
    name: str | None = None
    documentation: str = ""
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class DataObjectSpec(BaseModel):
    id: str
    name: str
    kind: str
    source_node_ref: str | None = None
    documentation: str = ""
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)
    mapping_status: MappingStatus = "semantic_payload"


class AnnotationSpec(BaseModel):
    id: str
    text: str
    source_node_ref: str | None = None
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class BusinessRuleSpec(BaseModel):
    id: str
    text: str
    target_ref: str | None = None
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class ExceptionPathSpec(BaseModel):
    id: str
    name: str
    trigger: str | None = None
    handling: str | None = None
    mapping_status: MappingStatus = "visual_annotation"
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class LoopSpec(BaseModel):
    id: str
    name: str
    repeated_steps: list[str] = Field(default_factory=list)
    condition: str | None = None
    exit_condition: str | None = None
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class HandoffSpec(BaseModel):
    id: str
    from_actor_id: str | None = None
    to_actor_id: str | None = None
    artifact: str | None = None
    trigger: str | None = None
    mapping_status: MappingStatus = "visual_annotation"
    source_refs: list[ProcessUnderstandingRef] = Field(default_factory=list)


class BpmnCompilationPlan(BaseModel):
    schema_version: str = "bpmn_compilation_plan.v1"
    process_id: str
    process_name: str
    participants: list[ParticipantSpec] = Field(default_factory=list)
    lanes: list[LaneSpec] = Field(default_factory=list)
    events: list[EventSpec] = Field(default_factory=list)
    activities: list[ActivitySpec] = Field(default_factory=list)
    gateways: list[GatewaySpec] = Field(default_factory=list)
    flows: list[FlowSpec] = Field(default_factory=list)
    data_objects: list[DataObjectSpec] = Field(default_factory=list)
    annotations: list[AnnotationSpec] = Field(default_factory=list)
    business_rules: list[BusinessRuleSpec] = Field(default_factory=list)
    exceptions: list[ExceptionPathSpec] = Field(default_factory=list)
    loops: list[LoopSpec] = Field(default_factory=list)
    handoffs: list[HandoffSpec] = Field(default_factory=list)
    coverage: CompilationCoverageReport


class BPMNSemanticModel(BaseModel):
    id: str
    name: str
    isExecutable: bool = False
    collaborationId: str | None = None
    participants: list[BPMNParticipant] = Field(default_factory=list)
    lanes: list[BPMNLane] = Field(default_factory=list)
    flowNodes: list[BPMNFlowNode]
    sequenceFlows: list[BPMNSequenceFlow]
    messageFlows: list[BPMNMessageFlow] = Field(default_factory=list)
    dataObjects: list[BPMNDataObject] = Field(default_factory=list)
    textAnnotations: list[BPMNTextAnnotation] = Field(default_factory=list)
    associations: list[BPMNAssociation] = Field(default_factory=list)
    model_warnings: list[str] = Field(default_factory=list)
    compilationPlan: BpmnCompilationPlan | None = None
    sourceProcessUnderstanding: dict | None = None


def build_bpmn_semantic_model(
    *,
    process_id: str,
    process_name: str,
    process: ProcessUnderstanding,
) -> BPMNSemanticModel:
    used_ids: set[str] = set()
    safe_process_id = _xml_id(process_id, "Process", used_ids)
    collaboration = _build_collaboration_layer(process, safe_process_id, used_ids)
    lanes = collaboration.lanes
    lane_by_actor_id = collaboration.lane_by_actor_id
    step_by_id = {step.id: step for step in process.steps}
    ordered_chain = _ordered_chain_items(process, step_by_id)

    nodes: list[BPMNFlowNode] = [
        BPMNFlowNode(id=_xml_id("StartEvent_1", "StartEvent", used_ids), type="startEvent", name=_start_name(process)),
    ]
    warnings = _semantic_warnings(
        process, lanes, collaboration_built=collaboration.collaboration_id is not None
    )
    warnings.extend(collaboration.warnings)
    registry = _FlowRegistry(
        used_ids=used_ids,
        edges_by_original=_sequence_flow_edges_by_endpoint(process),
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
        lane_id = _lane_for_step(step, process.actors, lane_by_actor_id)
        if _step_is_external_only(step, collaboration.external_actor_ids):
            warnings.append(
                f"Attivita '{step.label}' e assegnata solo a un partecipante esterno: "
                "verificare se appartiene al pool esterno o va resa un message flow."
            )
        task = BPMNFlowNode(
            id=_xml_id(step.id or f"Task_{index}", "Task", used_ids),
            type=_task_type(step),
            name=step.label,
            laneId=lane_id,
            owner=_actor_label(process.actors, step.actor_ids),
            documentation=_step_documentation(step, process.actors),
            sourceRefs=[_source_ref_id("steps", step.id)],
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

    end = BPMNFlowNode(
        id=_xml_id("EndEvent_1", "EndEvent", used_ids),
        type="endEvent",
        name=_end_name(process),
    )
    nodes.append(end)
    main_chain.append(end.id)
    for event in process.events:
        if event.type == "end":
            registry.map(event.id, end.id)

    registry.gateway_ids = {node.id for node in nodes if node.type.endswith("Gateway")}
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
        actors=process.actors,
        lane_by_actor_id=lane_by_actor_id,
        warnings=warnings,
    )
    _add_loop_flows(
        process=process,
        registry=registry,
        step_node_by_original_id=step_node_by_original_id,
        warnings=warnings,
    )
    _complete_flow_graph(process, registry, nodes, warnings)
    _add_boundary_events(
        process=process,
        registry=registry,
        nodes=nodes,
        step_node_by_original_id=step_node_by_original_id,
        step_by_id=step_by_id,
        lane_by_actor_id=lane_by_actor_id,
        actors=process.actors,
        used_ids=used_ids,
        end_id=end.id,
        warnings=warnings,
    )
    registry.apply_edge_overlay()
    flows = registry.flows
    _assign_gateway_defaults(nodes, flows, warnings)
    _populate_lane_refs(lanes, nodes)
    message_flows = _finalize_message_flows(
        collaboration=collaboration,
        step_node_by_original_id=step_node_by_original_id,
        node_ids={node.id for node in nodes},
        used_ids=used_ids,
        warnings=warnings,
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
        dataObjects=[],
        textAnnotations=[],
        associations=[],
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
            "Compilazione BPMN non lossless: "
            + "; ".join(model.compilationPlan.coverage.losses)
        )
    return model


def validate_bpmn_semantic_model(model: BPMNSemanticModel) -> list[str]:
    warnings: list[str] = []
    node_ids = {node.id for node in model.flowNodes}
    flow_ids = {flow.id for flow in model.sequenceFlows}
    data_ids = {item.id for item in model.dataObjects}
    annotation_ids = {item.id for item in model.textAnnotations}
    semantic_element_ids = node_ids | data_ids | annotation_ids
    if len(node_ids) != len(model.flowNodes) or len(flow_ids) != len(model.sequenceFlows):
        warnings.append("Sono presenti ID duplicati nel modello semantico.")
    if not any(node.type == "startEvent" for node in model.flowNodes):
        warnings.append("Manca un evento iniziale BPMN.")
    if not any(node.type == "endEvent" for node in model.flowNodes):
        warnings.append("Manca un evento finale BPMN.")

    outgoing_by_node = {node.id: [] for node in model.flowNodes}
    incoming_by_node = {node.id: [] for node in model.flowNodes}
    for flow in model.sequenceFlows:
        if flow.sourceRef not in node_ids or flow.targetRef not in node_ids:
            warnings.append(f"Sequence flow {flow.id} punta a un nodo inesistente.")
            continue
        outgoing_by_node[flow.sourceRef].append(flow)
        incoming_by_node[flow.targetRef].append(flow)

    for association in model.associations:
        if association.sourceRef not in semantic_element_ids or association.targetRef not in semantic_element_ids:
            warnings.append(f"Association {association.id} punta a un elemento inesistente.")

    node_type_by_id = {node.id: node.type for node in model.flowNodes}
    for node in model.flowNodes:
        if node.type == "exclusiveGateway" and len(outgoing_by_node.get(node.id, [])) < 2:
            warnings.append(f"Gateway {node.name} senza almeno due uscite.")
        if node.type == "boundaryEvent":
            if node_type_by_id.get(node.attachedToRef or "") not in _ACTIVITY_NODE_TYPES:
                warnings.append(f"Boundary event {node.name} non agganciato a un'attivita valida.")
            if not outgoing_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} senza gestione collegata.")
            if incoming_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} non puo' avere frecce in ingresso.")
            continue
        if node.type == "startEvent" and incoming_by_node.get(node.id):
            warnings.append(f"Evento iniziale {node.name} con una freccia in ingresso.")
        if node.type != "startEvent" and not incoming_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza ingresso.")
        if node.type == "endEvent" and outgoing_by_node.get(node.id):
            warnings.append(f"Evento finale {node.name} con una freccia in uscita.")
        if node.type != "endEvent" and not outgoing_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza uscita.")
    return warnings


def semantic_model_to_bpmn_xml(model: BPMNSemanticModel, *, visual_artifacts: bool = False) -> str:
    incoming, outgoing = _flow_refs(model)
    visual_data_objects = model.dataObjects if visual_artifacts else []
    annotations, associations = _semantic_annotations(model) if visual_artifacts else ([], [])
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'id="Definitions_{escape(model.id)}" targetNamespace="https://workspace.local/bpmn">',
    ]
    xml_parts.extend(_collaboration_semantic_xml(model))
    xml_parts.append(
        f'  <bpmn:process id="{escape(model.id)}" name="{escape(model.name)}" isExecutable="false">'
    )
    process_documentation = _process_documentation(model)
    if process_documentation:
        xml_parts.extend(_documentation_xml(process_documentation, indent="    "))

    if model.lanes:
        xml_parts.append(f'    <bpmn:laneSet id="{escape(model.id)}_LaneSet">')
        for lane in model.lanes:
            xml_parts.append(f'      <bpmn:lane id="{escape(lane.id)}" name="{escape(lane.name)}">')
            for ref in lane.flowNodeRefs:
                xml_parts.append(f"        <bpmn:flowNodeRef>{escape(ref)}</bpmn:flowNodeRef>")
            xml_parts.append("      </bpmn:lane>")
        xml_parts.append("    </bpmn:laneSet>")

    for node in model.flowNodes:
        attrs = f' id="{escape(node.id)}" name="{escape(node.name)}"'
        if node.type == "boundaryEvent" and node.attachedToRef:
            attrs += f' attachedToRef="{escape(node.attachedToRef)}"'
            if not node.cancelActivity:
                attrs += ' cancelActivity="false"'
        if node.defaultFlowId and node.type in {"exclusiveGateway", "inclusiveGateway"}:
            attrs += f' default="{escape(node.defaultFlowId)}"'
        xml_parts.append(f"    <bpmn:{node.type}{attrs}>")
        if node.documentation or node.sourceRefs:
            xml_parts.extend(_documentation_xml(_element_documentation(node.documentation, node.sourceRefs), indent="      "))
        if node.type != "boundaryEvent":
            for flow_id in incoming[node.id]:
                xml_parts.append(f"      <bpmn:incoming>{escape(flow_id)}</bpmn:incoming>")
        for flow_id in outgoing[node.id]:
            xml_parts.append(f"      <bpmn:outgoing>{escape(flow_id)}</bpmn:outgoing>")
        if node.type in {"intermediateCatchEvent", "boundaryEvent"} and node.eventDefinition:
            xml_parts.append(f"      <bpmn:{node.eventDefinition}EventDefinition />")
        xml_parts.append(f"    </bpmn:{node.type}>")

    for flow in model.sequenceFlows:
        name = f' name="{escape(flow.name)}"' if flow.name else ""
        body: list[str] = []
        if flow.documentation or flow.sourceRefs:
            body.extend(
                _documentation_xml(
                    _element_documentation(flow.documentation, flow.sourceRefs), indent="      "
                )
            )
        if flow.conditionExpression:
            body.append(
                '      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                f"{escape(flow.conditionExpression)}</bpmn:conditionExpression>"
            )
        open_tag = (
            f'    <bpmn:sequenceFlow id="{escape(flow.id)}" '
            f'sourceRef="{escape(flow.sourceRef)}" targetRef="{escape(flow.targetRef)}"{name}'
        )
        if body:
            xml_parts.append(open_tag + ">")
            xml_parts.extend(body)
            xml_parts.append("    </bpmn:sequenceFlow>")
        else:
            xml_parts.append(open_tag + " />")

    for data_object in visual_data_objects:
        if data_object.documentation or data_object.sourceRefs:
            xml_parts.append(
                f'    <bpmn:dataObjectReference id="{escape(data_object.id)}" name="{escape(data_object.name)}">'
            )
            xml_parts.extend(
                _documentation_xml(
                    _element_documentation(data_object.documentation, data_object.sourceRefs),
                    indent="      ",
                )
            )
            xml_parts.append("    </bpmn:dataObjectReference>")
        else:
            xml_parts.append(
                f'    <bpmn:dataObjectReference id="{escape(data_object.id)}" name="{escape(data_object.name)}" />'
            )
    for annotation in annotations:
        xml_parts.extend(
            [
                f'    <bpmn:textAnnotation id="{annotation["id"]}">',
                f'      <bpmn:text>{escape(annotation["text"])}</bpmn:text>',
                "    </bpmn:textAnnotation>",
            ]
        )
    for association in associations:
        xml_parts.append(
            f'    <bpmn:association id="{association["id"]}" sourceRef="{association["source"]}" targetRef="{association["target"]}" />'
        )

    plane_element = (
        (model.collaborationId or f"Collaboration_{model.id}") if model.participants else model.id
    )
    xml_parts.extend(
        [
            "  </bpmn:process>",
            f'  <bpmndi:BPMNDiagram id="BPMNDiagram_{escape(model.id)}">',
            f'    <bpmndi:BPMNPlane id="BPMNPlane_{escape(model.id)}" bpmnElement="{escape(plane_element)}">',
        ]
    )
    positions, lane_shapes = _layout_model(model)
    pool_shapes, pool_positions = _collaboration_pool_shapes(model, positions, lane_shapes)
    for pool_shape in pool_shapes:
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{pool_shape["id"]}_di" bpmnElement="{pool_shape["id"]}" isHorizontal="true">',
                f'        <dc:Bounds x="{pool_shape["x"]}" y="{pool_shape["y"]}" width="{pool_shape["width"]}" height="{pool_shape["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )
    for lane_shape in lane_shapes:
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{lane_shape["id"]}_di" bpmnElement="{lane_shape["id"]}" isHorizontal="true">',
                f'        <dc:Bounds x="{lane_shape["x"]}" y="{lane_shape["y"]}" width="{lane_shape["width"]}" height="{lane_shape["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )
    for node in model.flowNodes:
        pos = positions[node.id]
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{node.id}_di" bpmnElement="{node.id}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    data_positions = _layout_data_objects(visual_data_objects, positions)
    for data_object in visual_data_objects:
        pos = data_positions[data_object.id]
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{data_object.id}_di" bpmnElement="{data_object.id}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    annotation_positions = _layout_text_annotations(annotations)
    for annotation in annotations:
        pos = annotation_positions[annotation["id"]]
        xml_parts.extend(
            [
                f'      <bpmndi:BPMNShape id="{annotation["id"]}_di" bpmnElement="{annotation["id"]}">',
                f'        <dc:Bounds x="{pos["x"]}" y="{pos["y"]}" width="{pos["width"]}" height="{pos["height"]}" />',
                "      </bpmndi:BPMNShape>",
            ]
        )

    for flow in model.sequenceFlows:
        for line in _edge_xml(flow.id, flow.sourceRef, flow.targetRef, positions, flow.name):
            xml_parts.append(line)
    connectable_positions = {**positions, **data_positions, **annotation_positions}
    for association in associations:
        if association["source"] in connectable_positions and association["target"] in connectable_positions:
            for line in _association_edge_xml(association, connectable_positions):
                xml_parts.append(line)

    message_flow_positions = {**positions, **pool_positions}
    for message_flow in model.messageFlows:
        source_pos = message_flow_positions.get(message_flow.sourceRef)
        target_pos = message_flow_positions.get(message_flow.targetRef)
        if source_pos and target_pos:
            for line in _message_flow_edge_xml(message_flow, source_pos, target_pos):
                xml_parts.append(line)

    xml_parts.extend(["    </bpmndi:BPMNPlane>", "  </bpmndi:BPMNDiagram>", "</bpmn:definitions>"])
    return "\n".join(xml_parts)


def _collaboration_semantic_xml(model: BPMNSemanticModel) -> list[str]:
    if not model.participants:
        return []

    collaboration_id = model.collaborationId or f"Collaboration_{model.id}"
    lines = [f'  <bpmn:collaboration id="{escape(collaboration_id)}">']
    for participant in model.participants:
        process_ref = (
            f' processRef="{escape(participant.processRef)}"' if participant.processRef else ""
        )
        lines.append(
            f'    <bpmn:participant id="{escape(participant.id)}" '
            f'name="{escape(participant.name)}"{process_ref} />'
        )
    for message_flow in model.messageFlows:
        name = f' name="{escape(message_flow.name)}"' if message_flow.name else ""
        header = (
            f'    <bpmn:messageFlow id="{escape(message_flow.id)}" '
            f'sourceRef="{escape(message_flow.sourceRef)}" '
            f'targetRef="{escape(message_flow.targetRef)}"{name}'
        )
        if message_flow.documentation or message_flow.sourceRefs:
            lines.append(header + ">")
            lines.extend(
                _documentation_xml(
                    _element_documentation(message_flow.documentation, message_flow.sourceRefs),
                    indent="      ",
                )
            )
            lines.append("    </bpmn:messageFlow>")
        else:
            lines.append(header + " />")
    lines.append("  </bpmn:collaboration>")
    return lines


def _collaboration_pool_shapes(
    model: BPMNSemanticModel,
    node_positions: dict[str, dict[str, float]],
    lane_shapes: list[dict[str, float | str]],
) -> tuple[list[dict[str, float | str]], dict[str, dict[str, float]]]:
    if not model.participants:
        return [], {}

    primary = next((p for p in model.participants if p.processRef), None)
    externals = [p for p in model.participants if not p.processRef]

    # Cover both the lane band and the flow-node band so lanes never protrude.
    boxes: list[tuple[float, float, float, float]] = [
        (float(shape["x"]), float(shape["y"]), float(shape["width"]), float(shape["height"]))
        for shape in lane_shapes
    ]
    boxes.extend(
        (pos["x"], pos["y"], pos["width"], pos["height"]) for pos in node_positions.values()
    )
    if boxes:
        min_x = min(box[0] for box in boxes)
        min_y = min(box[1] for box in boxes)
        max_x = max(box[0] + box[2] for box in boxes)
        max_y = max(box[1] + box[3] for box in boxes)
    else:
        min_x, min_y, max_x, max_y = 110.0, 150.0, 1000.0, 330.0

    pool_left = min_x - 30
    pool_width = (max_x - pool_left) + 40
    primary_top = min_y - 30
    primary_height = max(max_y - primary_top + 30, 160.0)

    shapes: list[dict[str, float | str]] = []
    pool_positions: dict[str, dict[str, float]] = {}
    if primary is not None:
        box = {"x": pool_left, "y": primary_top, "width": pool_width, "height": primary_height}
        pool_positions[primary.id] = box
        shapes.append({"id": primary.id, **box})

    external_top = primary_top + primary_height + 40
    for participant in externals:
        box = {"x": pool_left, "y": external_top, "width": pool_width, "height": 120.0}
        pool_positions[participant.id] = box
        shapes.append({"id": participant.id, **box})
        external_top += 160

    return shapes, pool_positions


def _message_flow_edge_xml(
    message_flow: BPMNMessageFlow,
    source: dict[str, float],
    target: dict[str, float],
) -> list[str]:
    start_x = source["x"] + source["width"] / 2
    end_x = target["x"] + target["width"] / 2
    if source["y"] <= target["y"]:
        start_y = source["y"] + source["height"]
        end_y = target["y"]
    else:
        start_y = source["y"]
        end_y = target["y"] + target["height"]
    lines = [
        f'      <bpmndi:BPMNEdge id="{escape(message_flow.id)}_di" bpmnElement="{escape(message_flow.id)}">',
        f'        <di:waypoint x="{start_x}" y="{start_y}" />',
        f'        <di:waypoint x="{end_x}" y="{end_y}" />',
    ]
    if message_flow.name:
        label_width = min(180, max(80, len(message_flow.name) * 6))
        lines.extend(
            [
                "        <bpmndi:BPMNLabel>",
                f'          <dc:Bounds x="{(start_x + end_x) / 2 - label_width / 2}" '
                f'y="{(start_y + end_y) / 2 - 12}" width="{label_width}" height="24" />',
                "        </bpmndi:BPMNLabel>",
            ]
        )
    lines.append("      </bpmndi:BPMNEdge>")
    return lines


@dataclass
class _MessageFlowSpec:
    key: str
    label: str
    from_pool_key: str | None
    to_pool_key: str | None
    from_node_ref: str | None
    to_node_ref: str | None
    artifact: str | None


@dataclass
class _CollaborationLayer:
    collaboration_id: str | None
    participants: list[BPMNParticipant]
    lanes: list[BPMNLane]
    lane_by_actor_id: dict[str, str]
    message_flow_specs: list[_MessageFlowSpec]
    pool_id_by_key: dict[str, str]
    external_actor_ids: set[str]
    warnings: list[str] = field(default_factory=list)


def _build_collaboration_layer(
    process: ProcessUnderstanding,
    safe_process_id: str,
    used_ids: set[str],
) -> _CollaborationLayer:
    resolved = resolve_pool_topology(
        topology=process.bpmn_topology,
        participants=process.participants,
        actors=process.actors,
    )
    if not resolved.is_collaboration or resolved.primary_pool is None:
        lanes = _build_lanes(process.actors, used_ids)
        return _CollaborationLayer(
            collaboration_id=None,
            participants=[],
            lanes=lanes,
            lane_by_actor_id=_lane_by_actor_id(process.actors, lanes),
            message_flow_specs=[],
            pool_id_by_key={},
            external_actor_ids=set(),
            warnings=list(resolved.warnings),
        )

    primary = resolved.primary_pool
    pool_id_by_key: dict[str, str] = {}
    participants: list[BPMNParticipant] = []
    for pool in resolved.pools:
        participant_id = _xml_id(
            pool.participant_id or pool.label or pool.key, "Participant", used_ids
        )
        pool_id_by_key[pool.key] = participant_id
        participants.append(
            BPMNParticipant(
                id=participant_id,
                name=pool.label,
                processRef=safe_process_id if pool.is_primary else None,
                isExternal=pool.is_external and not pool.is_primary,
                rendering=pool.rendering,
                sourceRefs=[_source_ref_id("bpmn_topology", pool.key)],
            )
        )

    lanes, lane_by_actor_id = _lanes_for_primary_pool(resolved, primary, process.actors, used_ids)
    external_actor_ids = {
        actor_id
        for actor_id, pool_key in resolved.actor_to_pool.items()
        if pool_key != primary.key
    }
    specs = [
        _MessageFlowSpec(
            key=flow.key,
            label=flow.label,
            from_pool_key=flow.from_pool_key,
            to_pool_key=flow.to_pool_key,
            from_node_ref=flow.from_node_ref,
            to_node_ref=flow.to_node_ref,
            artifact=flow.artifact,
        )
        for flow in resolved.message_flows
    ]
    return _CollaborationLayer(
        collaboration_id=_xml_id(f"Collaboration_{safe_process_id}", "Collaboration", used_ids),
        participants=participants,
        lanes=lanes,
        lane_by_actor_id=lane_by_actor_id,
        message_flow_specs=specs,
        pool_id_by_key=pool_id_by_key,
        external_actor_ids=external_actor_ids,
        warnings=list(resolved.warnings),
    )


def _lanes_for_primary_pool(
    resolved: PoolTopology,
    primary: ResolvedPool,
    actors: list[ProcessActor],
    used_ids: set[str],
) -> tuple[list[BPMNLane], dict[str, str]]:
    lane_by_actor_id: dict[str, str] = {}
    lanes: list[BPMNLane] = []
    primary_lanes = [lane for lane in resolved.lanes if lane.pool_key == primary.key]
    if primary_lanes:
        for lane in primary_lanes:
            lane_id = _xml_id(lane.key or lane.label, "Lane", used_ids)
            lanes.append(
                BPMNLane(
                    id=lane_id,
                    name=lane.label,
                    sourceRefs=[_source_ref_id("bpmn_topology", lane.key)],
                )
            )
            for actor_id in lane.actor_ids:
                lane_by_actor_id.setdefault(actor_id, lane_id)
        return lanes, lane_by_actor_id

    actor_label = {actor.id: actor.label for actor in actors}
    for actor_id in primary.actor_ids:
        label = actor_label.get(actor_id, actor_id)
        if not label.strip():
            continue
        lane_id = _xml_id(actor_id or label, "Lane", used_ids)
        lanes.append(
            BPMNLane(id=lane_id, name=label, sourceRefs=[_source_ref_id("actors", actor_id)])
        )
        lane_by_actor_id[actor_id] = lane_id
    return lanes[:8], lane_by_actor_id


def _step_is_external_only(step: ProcessStep, external_actor_ids: set[str]) -> bool:
    if not external_actor_ids or not step.actor_ids:
        return False
    return all(actor_id in external_actor_ids for actor_id in step.actor_ids)


def _finalize_message_flows(
    *,
    collaboration: _CollaborationLayer,
    step_node_by_original_id: dict[str, str],
    node_ids: set[str],
    used_ids: set[str],
    warnings: list[str],
) -> list[BPMNMessageFlow]:
    result: list[BPMNMessageFlow] = []
    for spec in collaboration.message_flow_specs:
        source_ref = _message_endpoint(
            spec.from_node_ref, spec.from_pool_key, collaboration, step_node_by_original_id, node_ids
        )
        target_ref = _message_endpoint(
            spec.to_node_ref, spec.to_pool_key, collaboration, step_node_by_original_id, node_ids
        )
        if not source_ref or not target_ref or source_ref == target_ref:
            warnings.append(
                f"Message flow '{spec.label}' non collegato: estremi non risolti nel modello BPMN."
            )
            continue
        result.append(
            BPMNMessageFlow(
                id=_xml_id(spec.key or f"MessageFlow_{len(result) + 1}", "MessageFlow", used_ids),
                sourceRef=source_ref,
                targetRef=target_ref,
                name=spec.label,
                documentation=_json_documentation(
                    "message_flow", {"artifact": spec.artifact, "label": spec.label}
                ),
                sourceRefs=[_source_ref_id("bpmn_topology", spec.key)],
            )
        )
    return result


def _message_endpoint(
    node_ref: str | None,
    pool_key: str | None,
    collaboration: _CollaborationLayer,
    step_node_by_original_id: dict[str, str],
    node_ids: set[str],
) -> str | None:
    if node_ref:
        if node_ref in node_ids:
            return node_ref
        mapped = step_node_by_original_id.get(node_ref)
        if mapped:
            return mapped
    if pool_key and pool_key in collaboration.pool_id_by_key:
        return collaboration.pool_id_by_key[pool_key]
    return None


def _build_lanes(actors: list[ProcessActor], used_ids: set[str]) -> list[BPMNLane]:
    return [
        BPMNLane(
            id=_xml_id(actor.id or actor.label, "Lane", used_ids),
            name=actor.label,
            sourceRefs=[_source_ref_id("actors", actor.id)],
        )
        for actor in actors
        if actor.label.strip()
    ][:8]


def _lane_by_actor_id(actors: list[ProcessActor], lanes: list[BPMNLane]) -> dict[str, str]:
    lane_by_source_ref: dict[str, str] = {}
    for lane in lanes:
        for source_ref in lane.sourceRefs:
            lane_by_source_ref[source_ref] = lane.id
    return {
        actor.id: lane_by_source_ref[_source_ref_id("actors", actor.id)]
        for actor in actors
        if _source_ref_id("actors", actor.id) in lane_by_source_ref
    }


def _lane_for_step(
    step: ProcessStep,
    actors: list[ProcessActor],
    lane_by_actor_id: dict[str, str],
) -> str | None:
    for actor_id in step.actor_ids:
        if actor_id in lane_by_actor_id:
            return lane_by_actor_id[actor_id]
    return None


def _populate_lane_refs(lanes: list[BPMNLane], nodes: list[BPMNFlowNode]) -> None:
    lane_by_id = {lane.id: lane for lane in lanes}
    for node in nodes:
        if node.laneId and node.laneId in lane_by_id and node.id not in lane_by_id[node.laneId].flowNodeRefs:
            lane_by_id[node.laneId].flowNodeRefs.append(node.id)


def _task_type(step: ProcessStep) -> str:
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


_INTERMEDIATE_EVENT_DEFINITION: dict[str, Literal["timer", "message"]] = {
    "timer": "timer",
    "message": "message",
}


def _ordered_chain_items(
    process: ProcessUnderstanding,
    step_by_id: dict[str, ProcessStep],
) -> list[ProcessStep | ProcessEvent]:
    """Ordered list of flow nodes for the main path: steps plus the timer /
    message intermediate events that sit between them.

    Events are placed from `main_success_path` / `sequence` when listed there,
    otherwise spliced in after the predecessor named by a `flow_edges` entry.
    """
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
            insert_at = next(
                index for index, item in enumerate(chain) if item.id == predecessor
            ) + 1
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
    registry: _FlowRegistry,
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    gateway_by_step_id: dict[str, BPMNFlowNode],
) -> None:
    decision = decision_by_anchor_step_id.get(anchor_id)
    if decision is None:
        return
    gateway = BPMNFlowNode(
        id=_xml_id(decision.id, "Gateway", used_ids),
        type="exclusiveGateway",
        name=decision.label,
        laneId=lane_id,
        documentation=_decision_documentation(decision),
        sourceRefs=[_source_ref_id("decisions", decision.id)],
    )
    nodes.append(gateway)
    main_chain.append(gateway.id)
    registry.map(decision.id, gateway.id)
    gateway_by_decision_id[decision.id] = gateway
    gateway_by_step_id[anchor_id] = gateway


def _event_node(event: ProcessEvent, used_ids: set[str]) -> BPMNFlowNode:
    return BPMNFlowNode(
        id=_xml_id(event.id or "IntermediateEvent", "IntermediateEvent", used_ids),
        type="intermediateCatchEvent",
        name=event.label,
        eventDefinition=_INTERMEDIATE_EVENT_DEFINITION.get(event.type),
        documentation=_json_documentation(
            "event",
            {
                "type": event.type,
                "timing": event.timing,
                "source_evidence": event.source_evidence,
            },
        ),
        sourceRefs=[_source_ref_id("events", event.id)],
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
    for decision in decisions:
        if any(outcome.target_path_id == path.id for outcome in decision.outcome_details):
            return decision
    return None


def _anchor_step_for_decision(
    process: ProcessUnderstanding,
    decision: ProcessDecision,
    ordered_step_ids: list[str],
) -> str | None:
    for edge in process.flow_edges:
        if edge.target_id == decision.id and edge.source_id in ordered_step_ids:
            return edge.source_id
    return None


def _add_alternative_paths(
    *,
    process: ProcessUnderstanding,
    nodes: list[BPMNFlowNode],
    registry: _FlowRegistry,
    used_ids: set[str],
    step_by_id: dict[str, ProcessStep],
    step_node_by_original_id: dict[str, str],
    gateway_by_decision_id: dict[str, BPMNFlowNode],
    gateway_by_step_id: dict[str, BPMNFlowNode],
    actors: list[ProcessActor],
    lane_by_actor_id: dict[str, str],
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
        branch_node_ids = []
        for branch_index, step_id in enumerate(path.sequence, start=1):
            if step_id == path.rejoins_at and step_id in step_node_by_original_id:
                continue
            source_step = step_by_id.get(step_id)
            if source_step is None:
                warnings.append(f"Alternative path '{path.label}' cita step non trovato: {step_id}")
                continue
            lane_id = _lane_for_step(source_step, actors, lane_by_actor_id)
            branch_node = BPMNFlowNode(
                id=_xml_id(f"{path.id}_{source_step.id or branch_index}", "Task", used_ids),
                type=_task_type(source_step),
                name=source_step.label,
                laneId=lane_id,
                owner=_actor_label(actors, source_step.actor_ids),
            )
            nodes.append(branch_node)
            branch_node_ids.append(branch_node.id)
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
            alt_end = BPMNFlowNode(
                id=_xml_id(f"End_{path.id}", "EndEvent", used_ids),
                type="endEvent",
                name=path.ends_at or path.label or outcome_name or "Fine percorso alternativo",
                laneId=gateway.laneId,
            )
            nodes.append(alt_end)
            registry.add(previous_id, alt_end.id, name=path.trigger_or_condition)

        if not path.is_confirmed:
            warnings.append(f"Alternative path '{path.label}' non confermato.")

    if unassigned_paths and not gateways:
        warnings.append("Alternative path presenti, ma nessun gateway decisionale e' stato generato.")
    elif unassigned_paths:
        for path in unassigned_paths:
            warnings.append(f"Alternative path '{path.label}' non collegato a un outcome decisionale esplicito.")


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
    registry: _FlowRegistry,
    step_node_by_original_id: dict[str, str],
    warnings: list[str],
) -> None:
    for loop in process.loops:
        repeated = [step_id for step_id in loop.repeated_steps if step_id in step_node_by_original_id]
        if len(repeated) < 2:
            warnings.append(f"Loop '{loop.label}' presente ma non mappabile su almeno due step.")
            continue
        source_id = step_node_by_original_id[repeated[-1]]
        target_id = step_node_by_original_id[repeated[0]]
        added = registry.add(
            source_id,
            target_id,
            name=loop.condition or loop.label,
            documentation=_json_documentation(
                "loop",
                {
                    "label": loop.label,
                    "condition": loop.condition,
                    "exit_condition": loop.exit_condition,
                    "repeated_steps": loop.repeated_steps,
                },
            ),
            source_refs=[_source_ref_id("loops", loop.id)],
        )
        if added is None:
            warnings.append(
                f"Loop '{loop.label}' degenere (rientro su se stesso): non reso come freccia."
            )
        if loop.exit_condition:
            warnings.append(f"Loop '{loop.label}' con exit condition: {loop.exit_condition}")


_ACTIVITY_NODE_TYPES = frozenset(
    {
        "task",
        "userTask",
        "serviceTask",
        "manualTask",
        "sendTask",
        "receiveTask",
        "businessRuleTask",
        "scriptTask",
        "subProcess",
    }
)


def _add_boundary_events(
    *,
    process: ProcessUnderstanding,
    registry: _FlowRegistry,
    nodes: list[BPMNFlowNode],
    step_node_by_original_id: dict[str, str],
    step_by_id: dict[str, ProcessStep],
    lane_by_actor_id: dict[str, str],
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
            id=_xml_id(f"{exception_id}_Boundary", "BoundaryEvent", used_ids),
            type="boundaryEvent",
            name=exception.label,
            laneId=node_lane_by_id.get(attached),
            attachedToRef=attached,
            cancelActivity=interrupting,
            eventDefinition=definition,
            documentation=_json_documentation(
                "exception",
                {
                    "trigger": exception.trigger,
                    "handling": exception.handling,
                    "is_defined": exception.is_defined,
                },
            ),
            sourceRefs=[_source_ref_id("exceptions", exception_id)],
        )
        nodes.append(boundary)
        registry.map(exception_id, boundary.id)

        rejoin = _exception_rejoin_node(
            exception,
            process,
            registry,
            step_by_id=step_by_id,
            lane_by_actor_id=lane_by_actor_id,
            actors=actors,
            nodes=nodes,
            used_ids=used_ids,
            end_id=end_id,
            exception_source_ref=_source_ref_id("exceptions", exception_id),
        )
        if rejoin is not None and rejoin != boundary.id:
            registry.add(boundary.id, rejoin)
        elif exception.handling:
            handler_lane = node_lane_by_id.get(attached)
            handler = BPMNFlowNode(
                id=_xml_id(f"{exception_id}_Handler", "Task", used_ids),
                type="task",
                name=exception.handling[:80],
                laneId=handler_lane,
                sourceRefs=[_source_ref_id("exceptions", exception_id)],
            )
            handler_end = BPMNFlowNode(
                id=_xml_id(f"{exception_id}_End", "EndEvent", used_ids),
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
    registry: _FlowRegistry,
    step_node_by_original_id: dict[str, str],
    node_type_by_id: dict[str, str],
) -> str | None:
    def as_activity(node_id: str | None) -> str | None:
        if node_id and node_type_by_id.get(node_id) in _ACTIVITY_NODE_TYPES:
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
    registry: _FlowRegistry,
    *,
    step_by_id: dict[str, ProcessStep],
    lane_by_actor_id: dict[str, str],
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
                id=_xml_id(recovery_step.id or "RecoveryTask", "Task", used_ids),
                type=_task_type(recovery_step),
                name=recovery_step.label,
                laneId=_lane_for_step(recovery_step, actors, lane_by_actor_id),
                owner=_actor_label(actors, recovery_step.actor_ids),
                sourceRefs=[_source_ref_id("steps", recovery_step.id), exception_source_ref],
            )
            nodes.append(recovery)
            registry.map(recovery_step.id, recovery.id)
            # Give the freshly compiled recovery step an exit unless another
            # flow_edge already continues from it.
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
    lowered = text.casefold()
    return any(re.search(rf"\b{re.escape(word)}", lowered) for word in words)


def _build_data_objects(
    *,
    process: ProcessUnderstanding,
    used_ids: set[str],
    step_node_by_original_id: dict[str, str],
    ordered_steps: list[ProcessStep],
) -> tuple[list[BPMNDataObject], list[BPMNAssociation]]:
    data_objects: list[BPMNDataObject] = []
    associations: list[BPMNAssociation] = []

    for index, item in enumerate(process.data_objects, start=1):
        source_node_id = _source_node_for_data_object(
            label=item.label,
            step_node_by_original_id=step_node_by_original_id,
            ordered_steps=ordered_steps,
        )
        data_object = BPMNDataObject(
            id=_xml_id(item.id or f"DataObject_{index}", "DataObject", used_ids),
            name=item.label,
            kind=item.kind,
            sourceNodeRef=source_node_id,
            documentation=_json_documentation(
                "data_object",
                {
                    "kind": item.kind,
                    "source_evidence": item.source_evidence,
                },
            ),
            sourceRefs=[_source_ref_id("data_objects", item.id)],
        )
        data_objects.append(data_object)
        if source_node_id:
            associations.append(
                BPMNAssociation(
                    id=_xml_id(f"Association_{source_node_id}_to_{data_object.id}", "Association", used_ids),
                    sourceRef=source_node_id,
                    targetRef=data_object.id,
                )
            )

    return data_objects, associations


def _source_node_for_data_object(
    *,
    label: str,
    step_node_by_original_id: dict[str, str],
    ordered_steps: list[ProcessStep],
) -> str | None:
    _ = (label, step_node_by_original_id, ordered_steps)
    return None


def _build_process_annotations(
    *,
    process: ProcessUnderstanding,
    warnings: list[str],
    used_ids: set[str],
    source_node_id: str,
) -> tuple[list[BPMNTextAnnotation], list[BPMNAssociation]]:
    annotation_texts = []
    annotation_texts.extend(warnings[:4])
    annotation_texts.extend(
        f"Handoff: {item.artifact or item.trigger or item.id}"
        for item in process.handoffs
        if item.artifact or item.trigger or item.id
    )
    annotation_texts.extend(
        f"Pool candidate esterno: {item.actor_id}"
        for item in process.actor_relationships
        if item.bpmn_pool_candidate
    )
    annotation_texts.extend(f"Regola business: {item}" for item in process.business_rules)
    annotation_texts.extend(
        f"Domanda aperta ({item.severity}): {item.question}"
        for item in process.unknowns
    )
    annotation_texts.extend(
        f"Eccezione: {item.label}; trigger: {item.trigger or 'n/d'}; gestione: {item.handling or 'da definire'}"
        for item in process.exceptions
    )
    annotation_texts.extend(
        f"Hint BPMN: {item.element} - {item.hint} ({item.confidence})"
        for item in process.bpmn_modeling_hints
    )
    annotation_texts.extend(
        f"Evento {item.type}: {item.label}"
        for item in process.events
        if item.type not in {"start", "end"}
    )
    annotation_texts.extend(
        f"Input/output {item.step}: input={', '.join(item.input) or 'n/d'}; output={', '.join(item.output) or 'n/d'}"
        for item in process.input_outputs
    )

    annotations: list[BPMNTextAnnotation] = []
    associations: list[BPMNAssociation] = []
    for index, text in enumerate(_unique_texts(annotation_texts)[:30], start=1):
        annotation = BPMNTextAnnotation(
            id=_xml_id(f"TextAnnotation_{index}", "TextAnnotation", used_ids),
            text=text[:240],
            sourceNodeRef=source_node_id,
        )
        annotations.append(annotation)
        associations.append(
            BPMNAssociation(
                id=_xml_id(f"Association_{index}", "Association", used_ids),
                sourceRef=source_node_id,
                targetRef=annotation.id,
            )
        )
    return annotations, associations


@dataclass
class _FlowRegistry:
    """Single writer for sequence flows.

    Deduplicates by (source, target) so overlapping generators (linear chain,
    alternative-path branches, loop back-edges) cannot emit the same edge twice.
    A generator that hits an already-written pair still contributes its label /
    documentation / traceability to the existing flow instead of losing it.
    Generators call `map()` with the original source-model id of every node they
    create; `apply_edge_overlay()` then folds `flow_edges` labels and gateway
    conditions onto the compiled flows in one final pass.
    """

    used_ids: set[str]
    edges_by_original: dict[tuple[str, str], ProcessFlowEdge] = field(default_factory=dict)
    gateway_ids: set[str] = field(default_factory=set)
    flows: list[BPMNSequenceFlow] = field(default_factory=list)
    seen_pairs: set[tuple[str, str]] = field(default_factory=set)
    _compiled_by_original: dict[str, str] = field(default_factory=dict)
    _flow_by_pair: dict[tuple[str, str], BPMNSequenceFlow] = field(default_factory=dict)

    def map(self, original_id: str | None, compiled_id: str) -> None:
        if original_id:
            self._compiled_by_original.setdefault(original_id, compiled_id)

    def compiled_for(self, original_id: str) -> str | None:
        return self._compiled_by_original.get(original_id)

    def outgoing_count(self, node_id: str) -> int:
        return sum(1 for flow in self.flows if flow.sourceRef == node_id)

    def incoming_count(self, node_id: str) -> int:
        return sum(1 for flow in self.flows if flow.targetRef == node_id)

    def add(
        self,
        source: str,
        target: str,
        *,
        name: str | None = None,
        documentation: str | None = None,
        source_refs: list[str] | None = None,
    ) -> BPMNSequenceFlow | None:
        if not source or not target or source == target:
            return None
        pair = (source, target)
        existing = self._flow_by_pair.get(pair)
        if existing is not None:
            self._enrich(existing, name=name, documentation=documentation, source_refs=source_refs)
            return existing

        flow = BPMNSequenceFlow(
            id=_xml_id(f"Flow_{source}_to_{target}", "Flow", self.used_ids),
            sourceRef=source,
            targetRef=target,
            name=name,
            documentation=documentation,
            sourceRefs=list(source_refs or []),
        )
        self.flows.append(flow)
        self.seen_pairs.add(pair)
        self._flow_by_pair[pair] = flow
        return flow

    def connect_chain(self, chain: list[str]) -> None:
        for source, target in zip(chain, chain[1:]):
            self.add(source, target)

    def apply_edge_overlay(self) -> None:
        for (origin_source, origin_target), edge in self.edges_by_original.items():
            source = self._compiled_by_original.get(origin_source)
            target = self._compiled_by_original.get(origin_target)
            if source is None or target is None:
                continue
            flow = self._flow_by_pair.get((source, target))
            if flow is None:
                continue
            self._enrich(
                flow,
                name=edge.label.strip() or None,
                source_refs=[_source_ref_id("flow_edges", edge.id)],
            )
            if edge.condition and source in self.gateway_ids and not flow.conditionExpression:
                flow.conditionExpression = edge.condition

    @staticmethod
    def _enrich(
        flow: BPMNSequenceFlow,
        *,
        name: str | None = None,
        documentation: str | None = None,
        source_refs: list[str] | None = None,
    ) -> None:
        if name and not flow.name:
            flow.name = name
        if documentation and not flow.documentation:
            flow.documentation = documentation
        for ref in source_refs or []:
            if ref not in flow.sourceRefs:
                flow.sourceRefs.append(ref)


def _assign_gateway_defaults(
    nodes: list[BPMNFlowNode],
    flows: list[BPMNSequenceFlow],
    warnings: list[str],
) -> None:
    """Give data-based gateways a default flow.

    A BPMN exclusive/inclusive gateway with two or more outgoing flows must not
    leave a plain unconditioned branch: the branch with no condition becomes the
    default. When every branch is conditioned nothing is marked (the modeller
    owns that); when more than one is unconditioned it is reported.
    """
    outgoing: dict[str, list[BPMNSequenceFlow]] = {}
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


def _sequence_flow_edges_by_endpoint(process: ProcessUnderstanding) -> dict[tuple[str, str], ProcessFlowEdge]:
    index: dict[tuple[str, str], ProcessFlowEdge] = {}
    for edge in process.flow_edges:
        if edge.kind == "sequence":
            index.setdefault((edge.source_id, edge.target_id), edge)
    return index


def _complete_flow_graph(
    process: ProcessUnderstanding,
    registry: _FlowRegistry,
    nodes: list[BPMNFlowNode],
    warnings: list[str],
) -> None:
    """Add flow_edges transitions the skeleton generators missed.

    An addition is applied only when it cannot corrupt control flow: the target
    is never a start event and either routes into a gateway/event/end or would
    not become an uncontrolled merge (<=1 existing incoming); the source is a
    gateway (which may branch freely) or an activity that still has no outgoing
    flow. Everything else — a second exit from an activity, a merge onto a busy
    node — is reported so a gateway can be added instead of silently drawn.
    """
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


def build_bpmn_compilation_plan(
    *,
    process_id: str,
    process_name: str,
    process: ProcessUnderstanding,
    model: BPMNSemanticModel,
) -> BpmnCompilationPlan:
    target_by_source_ref = _target_by_source_ref(model)
    source_items = _process_source_items(process)
    traceability: list[TraceabilityLink] = []

    for item in source_items:
        source_ref_id = _source_ref_id(item.field, item.id)
        target = target_by_source_ref.get(source_ref_id)
        if target is None:
            target = (process_id, "process")
            status: MappingStatus = "semantic_payload"
            rationale = "Preserved losslessly in process-level BPMN documentation payload."
        else:
            status = "direct"
            rationale = "Mapped to a concrete BPMN model element."

        traceability.append(
            TraceabilityLink(
                source=item,
                target_id=target[0],
                target_type=target[1],
                mapping_status=status,
                rationale=rationale,
            )
        )

    coverage = CompilationCoverageReport(
        total_source_items=len(source_items),
        represented_source_items=len(traceability),
        losses=[],
        warnings=list(model.model_warnings),
        traceability=traceability,
    )

    return BpmnCompilationPlan(
        process_id=process_id,
        process_name=process_name,
        participants=[
            ParticipantSpec(
                id=actor.id,
                name=actor.label,
                kind=actor.kind,
                source_refs=[_source_ref("actors", actor.id, actor.label)],
                mapping_status="direct",
            )
            for actor in process.actors
        ],
        lanes=[
            LaneSpec(
                id=lane.id,
                name=lane.name,
                actor_id=next(
                    (actor.id for actor in process.actors if _xml_id_preview(actor.id or actor.label) == lane.id),
                    lane.id,
                ),
                source_refs=[_source_ref_from_id(ref) for ref in lane.sourceRefs],
            )
            for lane in model.lanes
        ],
        events=[
            EventSpec(
                id=node.id,
                name=node.name,
                type=node.type,
                documentation=node.documentation or "",
                source_refs=[_source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type in {"startEvent", "endEvent", "intermediateCatchEvent", "boundaryEvent"}
        ],
        activities=[
            ActivitySpec(
                id=node.id,
                name=node.name,
                type=node.type,
                lane_id=node.laneId,
                documentation=node.documentation or "",
                source_refs=[_source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type
            not in {
                "startEvent",
                "endEvent",
                "intermediateCatchEvent",
                "boundaryEvent",
                "exclusiveGateway",
                "parallelGateway",
            }
        ],
        gateways=[
            GatewaySpec(
                id=node.id,
                name=node.name,
                type="exclusiveGateway" if node.type == "exclusiveGateway" else "parallelGateway",
                anchor_step_id=_anchor_for_gateway(node.id, model),
                documentation=node.documentation or "",
                source_refs=[_source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type in {"exclusiveGateway", "parallelGateway"}
        ],
        flows=[
            FlowSpec(
                id=flow.id,
                source_ref=flow.sourceRef,
                target_ref=flow.targetRef,
                name=flow.name,
                documentation=flow.documentation or "",
                source_refs=[_source_ref_from_id(ref) for ref in flow.sourceRefs],
            )
            for flow in model.sequenceFlows
        ],
        data_objects=[
            DataObjectSpec(
                id=item.id,
                name=item.label,
                kind=item.kind,
                documentation=_json_documentation(
                    "data_object",
                    {
                        "kind": item.kind,
                        "source_evidence": item.source_evidence,
                    },
                ),
                source_refs=[_source_ref("data_objects", item.id, item.label)],
                mapping_status="semantic_payload",
            )
            for item in process.data_objects
        ],
        annotations=[
            AnnotationSpec(id=item.id, text=item.text, source_node_ref=item.sourceNodeRef)
            for item in model.textAnnotations
        ],
        business_rules=[
            BusinessRuleSpec(
                id=f"BusinessRule_{index}",
                text=rule,
                target_ref=model.textAnnotations[min(index - 1, len(model.textAnnotations) - 1)].id
                if model.textAnnotations
                else process_id,
                source_refs=[_source_ref("business_rules", str(index), rule)],
            )
            for index, rule in enumerate(process.business_rules, start=1)
        ],
        exceptions=[
            ExceptionPathSpec(
                id=item.id,
                name=item.label,
                trigger=item.trigger,
                handling=item.handling,
                source_refs=[_source_ref("exceptions", item.id, item.label)],
            )
            for item in process.exceptions
        ],
        loops=[
            LoopSpec(
                id=item.id,
                name=item.label,
                repeated_steps=item.repeated_steps,
                condition=item.condition,
                exit_condition=item.exit_condition,
                source_refs=[_source_ref("loops", item.id, item.label)],
            )
            for item in process.loops
        ],
        handoffs=[
            HandoffSpec(
                id=item.id,
                from_actor_id=item.from_actor_id,
                to_actor_id=item.to_actor_id,
                artifact=item.artifact,
                trigger=item.trigger,
                source_refs=[_source_ref("handoffs", item.id, item.artifact or item.trigger or item.id)],
            )
            for item in process.handoffs
        ],
        coverage=coverage,
    )


def _target_by_source_ref(model: BPMNSemanticModel) -> dict[str, tuple[str, str]]:
    targets: dict[str, tuple[str, str]] = {}
    for lane in model.lanes:
        for source_ref in lane.sourceRefs:
            targets[source_ref] = (lane.id, "lane")
    for node in model.flowNodes:
        for source_ref in node.sourceRefs:
            targets[source_ref] = (node.id, node.type)
    for flow in model.sequenceFlows:
        for source_ref in flow.sourceRefs:
            targets[source_ref] = (flow.id, "sequenceFlow")
    for data_object in model.dataObjects:
        for source_ref in data_object.sourceRefs:
            targets[source_ref] = (data_object.id, "dataObjectReference")
    return targets


def _process_source_items(process: ProcessUnderstanding) -> list[ProcessUnderstandingRef]:
    items: list[ProcessUnderstandingRef] = []
    scalar_fields = {
        "objective": process.objective,
        "scope": process.scope,
        "boundaries": process.boundaries.model_dump(mode="json") if process.boundaries else None,
        "bpmn_topology": process.bpmn_topology.model_dump(mode="json") if process.bpmn_topology else None,
        "narrative_focus": process.narrative_focus,
        "confidence": process.confidence.model_dump(mode="json") if process.confidence else None,
    }
    for field, value in scalar_fields.items():
        if value:
            items.append(ProcessUnderstandingRef(field=field, label=field))

    collection_fields = {
        "actors": process.actors,
        "events": process.events,
        "steps": process.steps,
        "sequence": process.sequence,
        "decisions": process.decisions,
        "handoffs": process.handoffs,
        "data_objects": process.data_objects,
        "participants": process.participants,
        "document_requirements": process.document_requirements,
        "input_outputs": process.input_outputs,
        "exceptions": process.exceptions,
        "controls": process.controls,
        "business_rules": process.business_rules,
        "structured_business_rules": process.structured_business_rules,
        "assumptions": process.assumptions,
        "unknowns": process.unknowns,
        "main_success_path": process.main_success_path,
        "alternative_paths": process.alternative_paths,
        "out_of_scope_alternatives": process.out_of_scope_alternatives,
        "flow_edges": process.flow_edges,
        "loops": process.loops,
        "actor_relationships": process.actor_relationships,
        "bpmn_modeling_hints": process.bpmn_modeling_hints,
    }
    for field, values in collection_fields.items():
        for index, value in enumerate(values, start=1):
            item_id = getattr(value, "id", None) or getattr(value, "actor_id", None) or str(index)
            label = getattr(value, "label", None) or getattr(value, "question", None) or str(value)
            items.append(ProcessUnderstandingRef(field=field, id=str(item_id), label=label))

    return items


def _source_ref(field: str, item_id: str | None, label: str | None = None) -> ProcessUnderstandingRef:
    return ProcessUnderstandingRef(field=field, id=item_id, label=label)


def _source_ref_id(field: str, item_id: str | None) -> str:
    return f"{field}:{item_id or '_'}"


def _source_ref_from_id(value: str) -> ProcessUnderstandingRef:
    field, _, item_id = value.partition(":")
    return ProcessUnderstandingRef(field=field or "unknown", id=item_id or None)


def _anchor_for_gateway(gateway_id: str, model: BPMNSemanticModel) -> str | None:
    for flow in model.sequenceFlows:
        if flow.targetRef == gateway_id:
            return flow.sourceRef
    return None


def _xml_id_preview(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return candidate[:70]


def _process_documentation(model: BPMNSemanticModel) -> str:
    payload = {
        "schema": "delir.semantic_payload.v1",
        "process_understanding": model.sourceProcessUnderstanding,
        "bpmn_compilation_plan": model.compilationPlan.model_dump(mode="json") if model.compilationPlan else None,
    }
    return "DeliR semantic payload:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _element_documentation(documentation: str | None, source_refs: list[str]) -> str:
    payload = {"source_refs": source_refs}
    parts = []
    if documentation:
        parts.append(documentation)
    if source_refs:
        parts.append("DeliR traceability:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n\n".join(parts)


def _step_documentation(step: ProcessStep, actors: list[ProcessActor]) -> str:
    return _json_documentation(
        "step",
        {
            "description": step.description,
            "actors": _actor_label(actors, step.actor_ids),
            "inputs": step.inputs,
            "outputs": step.outputs,
            "source_evidence": step.source_evidence,
        },
    )


def _decision_documentation(decision: ProcessDecision) -> str:
    return _json_documentation(
        "decision",
        {
            "question": decision.question,
            "outcomes": decision.outcomes,
            "source_evidence": decision.source_evidence,
        },
    )


def _json_documentation(kind: str, payload: dict) -> str:
    return f"DeliR {kind} context:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _documentation_xml(text: str, indent: str) -> list[str]:
    return [
        f"{indent}<bpmn:documentation>",
        f"{indent}  {escape(text)}",
        f"{indent}</bpmn:documentation>",
    ]


def _semantic_warnings(
    process: ProcessUnderstanding,
    lanes: list[BPMNLane],
    *,
    collaboration_built: bool = False,
) -> list[str]:
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


def _semantic_annotations(model: BPMNSemanticModel) -> tuple[list[dict], list[dict]]:
    annotations = [
        {"id": annotation.id, "text": annotation.text}
        for annotation in model.textAnnotations
    ]
    associations = [
        {"id": association.id, "source": association.sourceRef, "target": association.targetRef}
        for association in model.associations
    ]

    if not annotations and model.model_warnings:
        source = next((node.id for node in model.flowNodes if node.type not in {"startEvent", "endEvent"}), model.flowNodes[0].id)
        annotations = [
            {"id": f"TextAnnotation_{index}", "text": warning[:240]}
            for index, warning in enumerate(model.model_warnings[:4], start=1)
        ]
        associations = [
            {"id": f"Association_{index}", "source": source, "target": annotation["id"]}
            for index, annotation in enumerate(annotations, start=1)
        ]
    return annotations, associations


def _layout_model(model: BPMNSemanticModel) -> tuple[dict[str, dict[str, float]], list[dict[str, float | str]]]:
    lane_index_by_id = {lane.id: index for index, lane in enumerate(model.lanes)}
    lane_count = max(1, len(model.lanes))
    lane_height = 180
    top = 150
    left = 110
    lane_label_width = 70
    x_gap = 230
    positions: dict[str, dict[str, float]] = {}

    ranked_nodes = [node for node in model.flowNodes if node.type != "boundaryEvent"]
    for rank, node in enumerate(ranked_nodes):
        width, height = _node_size(node)
        lane_index = lane_index_by_id.get(node.laneId or "", 0)
        y = top + lane_index * lane_height + (lane_height - height) / 2
        positions[node.id] = {
            "x": left + lane_label_width + 70 + rank * x_gap,
            "y": y,
            "width": width,
            "height": height,
        }

    for node in model.flowNodes:
        if node.type != "boundaryEvent":
            continue
        width, height = _node_size(node)
        attached = positions.get(node.attachedToRef or "")
        if attached is not None:
            positions[node.id] = {
                "x": attached["x"] + attached["width"] * 0.62,
                "y": attached["y"] + attached["height"] - height / 2,
                "width": width,
                "height": height,
            }
        else:
            positions[node.id] = {"x": left, "y": top, "width": width, "height": height}

    right = max((pos["x"] + pos["width"] for pos in positions.values()), default=900) + 90
    lane_shapes = [
        {
            "id": lane.id,
            "x": left,
            "y": top + index * lane_height,
            "width": max(900, right - left),
            "height": lane_height,
        }
        for index, lane in enumerate(model.lanes)
    ]
    return positions, lane_shapes


def _layout_text_annotations(annotations: list[dict]) -> dict[str, dict[str, float]]:
    return {
        annotation["id"]: {
            "x": 180 + ((index - 1) * 230),
            "y": 40,
            "width": 190,
            "height": 70,
        }
        for index, annotation in enumerate(annotations, start=1)
    }


def _layout_data_objects(
    data_objects: list[BPMNDataObject],
    positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    layout = {}
    per_source_count: dict[str, int] = {}

    for index, data_object in enumerate(data_objects, start=1):
        source_id = data_object.sourceNodeRef or ""
        source = positions.get(source_id)
        if source:
            offset = per_source_count.get(source_id, 0)
            per_source_count[source_id] = offset + 1
            x = source["x"] + 20 + offset * 48
            y = source["y"] + source["height"] + 34
        else:
            x = 180 + (index - 1) * 130
            y = 420
        layout[data_object.id] = {"x": x, "y": y, "width": 64, "height": 54}

    return layout


def _edge_xml(
    flow_id: str,
    source_ref: str,
    target_ref: str,
    positions: dict[str, dict[str, float]],
    name: str | None,
) -> list[str]:
    source = positions[source_ref]
    target = positions[target_ref]
    start_x = source["x"] + source["width"]
    start_y = source["y"] + source["height"] / 2
    end_x = target["x"]
    end_y = target["y"] + target["height"] / 2
    lines = [
        f'      <bpmndi:BPMNEdge id="{escape(flow_id)}_di" bpmnElement="{escape(flow_id)}">',
        f'        <di:waypoint x="{start_x}" y="{start_y}" />',
    ]
    if abs(start_y - end_y) > 1:
        mid_x = start_x + max(60, (end_x - start_x) / 2)
        lines.extend(
            [
                f'        <di:waypoint x="{mid_x}" y="{start_y}" />',
                f'        <di:waypoint x="{mid_x}" y="{end_y}" />',
            ]
        )
    lines.extend(
        [
            f'        <di:waypoint x="{end_x}" y="{end_y}" />',
        ]
    )
    if name:
        label_width = min(150, max(70, len(name) * 6))
        lines.extend(
            [
                "        <bpmndi:BPMNLabel>",
                f'          <dc:Bounds x="{(start_x + end_x) / 2 - label_width / 2}" y="{min(start_y, end_y) - 32}" width="{label_width}" height="24" />',
                "        </bpmndi:BPMNLabel>",
            ]
        )
    lines.append("      </bpmndi:BPMNEdge>")
    return lines


def _association_edge_xml(
    association: dict,
    positions: dict[str, dict[str, float]],
) -> list[str]:
    source = positions[association["source"]]
    target = positions[association["target"]]
    return [
        f'      <bpmndi:BPMNEdge id="{association["id"]}_di" bpmnElement="{association["id"]}">',
        f'        <di:waypoint x="{source["x"] + source["width"] / 2}" y="{source["y"]}" />',
        f'        <di:waypoint x="{target["x"] + target["width"] / 2}" y="{target["y"] + target["height"]}" />',
        "      </bpmndi:BPMNEdge>",
    ]


def _flow_refs(model: BPMNSemanticModel) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    incoming = {node.id: [] for node in model.flowNodes}
    outgoing = {node.id: [] for node in model.flowNodes}
    for flow in model.sequenceFlows:
        outgoing.setdefault(flow.sourceRef, []).append(flow.id)
        incoming.setdefault(flow.targetRef, []).append(flow.id)
    return incoming, outgoing


def _node_size(node: BPMNFlowNode) -> tuple[int, int]:
    if node.type in {"startEvent", "endEvent", "intermediateCatchEvent"}:
        return 44, 44
    if node.type == "boundaryEvent":
        return 36, 36
    if node.type in {"exclusiveGateway", "parallelGateway"}:
        return 68, 68
    return 188, 92


def _start_name(process: ProcessUnderstanding) -> str:
    if process.boundaries and process.boundaries.start_event:
        return process.boundaries.start_event
    event = next((item for item in process.events if item.type == "start"), None)
    return event.label if event else "Start"


def _end_name(process: ProcessUnderstanding) -> str:
    if process.boundaries and process.boundaries.success_end:
        return process.boundaries.success_end
    event = next((item for item in process.events if item.type == "end"), None)
    return event.label if event else "End"


def _outcome_name_for_path(decision: ProcessDecision, path) -> str | None:
    for outcome in decision.outcome_details:
        if outcome.target_path_id == path.id:
            return outcome.label or outcome.condition
    return path.trigger_or_condition or path.label


def _actor_label(actors: list[ProcessActor], actor_ids: list[str]) -> str | None:
    by_id = {actor.id: actor.label for actor in actors}
    labels = [by_id[actor_id] for actor_id in actor_ids if actor_id in by_id]
    return ", ".join(labels) if labels else None


def _xml_id(value: str, prefix: str, used: set[str]) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not candidate or not re.match(r"^[A-Za-z_]", candidate):
        candidate = f"{prefix}_{candidate}" if candidate else prefix
    base = candidate[:70]
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _unique_texts(values: list[str]) -> list[str]:
    result = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in result:
            result.append(clean)
    return result
