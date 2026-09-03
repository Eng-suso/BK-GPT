"""Traceability: how every ProcessUnderstanding source item mapped into the
compiled BPMN model.
"""

from __future__ import annotations

from backend.bpmn._helpers import (
    json_documentation,
    source_ref,
    source_ref_from_id,
    source_ref_id,
)
from backend.bpmn.models import (
    ActivitySpec,
    AnnotationSpec,
    BpmnCompilationPlan,
    BPMNSemanticModel,
    BusinessRuleSpec,
    CompilationCoverageReport,
    DataObjectSpec,
    EventSpec,
    ExceptionPathSpec,
    FlowSpec,
    GatewaySpec,
    HandoffSpec,
    LaneSpec,
    LoopSpec,
    MappingStatus,
    ParticipantSpec,
    ProcessUnderstandingRef,
    TraceabilityLink,
)
from backend.process_understanding import ProcessUnderstanding

_EVENT_NODE_TYPES = {
    "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent"
}
_GATEWAY_NODE_TYPES = {
    "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"
}


def build_bpmn_compilation_plan(
    *,
    process_id: str,
    process_name: str,
    process: ProcessUnderstanding,
    model: BPMNSemanticModel,
) -> BpmnCompilationPlan:
    """Build a complete traceability plan from source ProcessUnderstanding to BPMN.

    Args:
        process_id: The identifier for the compiled process.
        process_name: The name of the process.
        process: The source ProcessUnderstanding model.
        model: The compiled BPMNSemanticModel.

    Returns:
        A BpmnCompilationPlan with full traceability and coverage reporting.
    """
    target_by_source_ref = _target_by_source_ref(model)
    source_items = _process_source_items(process)
    traceability: list[TraceabilityLink] = []

    for item in source_items:
        ref_id = source_ref_id(item.field, item.id)
        target = target_by_source_ref.get(ref_id)
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
                source_refs=[source_ref("actors", actor.id, actor.label)],
                mapping_status="direct",
            )
            for actor in process.actors
        ],
        lanes=[
            LaneSpec(
                id=lane.id,
                name=lane.name,
                actor_id=next(
                    (
                        ref.id
                        for ref in (source_ref_from_id(value) for value in lane.sourceRefs)
                        if ref.field == "actors" and ref.id
                    ),
                    lane.id,
                ),
                source_refs=[source_ref_from_id(ref) for ref in lane.sourceRefs],
            )
            for lane in model.lanes
        ],
        events=[
            EventSpec(
                id=node.id,
                name=node.name,
                type=node.type,
                documentation=node.documentation or "",
                source_refs=[source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type in _EVENT_NODE_TYPES
        ],
        activities=[
            ActivitySpec(
                id=node.id,
                name=node.name,
                type=node.type,
                lane_id=node.laneId,
                documentation=node.documentation or "",
                source_refs=[source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type
            not in _EVENT_NODE_TYPES | _GATEWAY_NODE_TYPES
        ],
        gateways=[
            GatewaySpec(
                id=node.id,
                name=node.name,
                type=node.type,
                anchor_step_id=_anchor_for_gateway(node.id, model),
                documentation=node.documentation or "",
                source_refs=[source_ref_from_id(ref) for ref in node.sourceRefs],
            )
            for node in model.flowNodes
            if node.type in _GATEWAY_NODE_TYPES
        ],
        flows=[
            FlowSpec(
                id=flow.id,
                source_ref=flow.sourceRef,
                target_ref=flow.targetRef,
                name=flow.name,
                documentation=flow.documentation or "",
                source_refs=[source_ref_from_id(ref) for ref in flow.sourceRefs],
            )
            for flow in model.sequenceFlows
        ],
        data_objects=[
            DataObjectSpec(
                id=item.id,
                name=item.label,
                kind=item.kind,
                documentation=json_documentation(
                    "data_object",
                    {
                        "kind": item.kind,
                        "source_evidence": item.source_evidence,
                    },
                ),
                source_refs=[source_ref("data_objects", item.id, item.label)],
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
                source_refs=[source_ref("business_rules", str(index), rule)],
            )
            for index, rule in enumerate(process.business_rules, start=1)
        ],
        exceptions=[
            ExceptionPathSpec(
                id=item.id,
                name=item.label,
                trigger=item.trigger,
                handling=item.handling,
                source_refs=[source_ref("exceptions", item.id, item.label)],
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
                source_refs=[source_ref("loops", item.id, item.label)],
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
                source_refs=[source_ref("handoffs", item.id, item.artifact or item.trigger or item.id)],
            )
            for item in process.handoffs
        ],
        coverage=coverage,
    )


def _target_by_source_ref(model: BPMNSemanticModel) -> dict[str, tuple[str, str]]:
    """Build an index from source reference IDs to their BPMN targets.

    Args:
        model: The BPMNSemanticModel to index.

    Returns:
        A dictionary mapping source reference IDs to (target_id, target_type) tuples.
    """
    targets: dict[str, tuple[str, str]] = {}
    for lane in model.lanes:
        for ref in lane.sourceRefs:
            targets[ref] = (lane.id, "lane")
    for node in model.flowNodes:
        for ref in node.sourceRefs:
            targets[ref] = (node.id, node.type)
    for flow in model.sequenceFlows:
        for ref in flow.sourceRefs:
            targets[ref] = (flow.id, "sequenceFlow")
    for data_object in model.dataObjects:
        for ref in data_object.sourceRefs:
            targets[ref] = (data_object.id, "dataObjectReference")
    return targets


def _process_source_items(process: ProcessUnderstanding) -> list[ProcessUnderstandingRef]:
    """Extract all source items from a ProcessUnderstanding for traceability.

    Args:
        process: The ProcessUnderstanding model to extract items from.

    Returns:
        A list of ProcessUnderstandingRef instances covering all source content.
    """
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


def _anchor_for_gateway(gateway_id: str, model: BPMNSemanticModel) -> str | None:
    """Find the anchor node (predecessor) for a gateway.

    Args:
        gateway_id: The ID of the gateway to find the anchor for.
        model: The BPMNSemanticModel containing the flows.

    Returns:
        The ID of the first node flowing into the gateway, or None if not found.
    """
    for flow in model.sequenceFlows:
        if flow.targetRef == gateway_id:
            return flow.sourceRef
    return None
