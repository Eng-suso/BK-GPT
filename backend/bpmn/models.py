"""Typed BPMN model — the intermediate representation the compiler produces and
the serializer consumes.

`BPMNSemanticModel` is DeliR's canonical BPMN IR: a `ProcessUnderstanding` is
compiled into one of these, it is validated and serialized to BPMN 2.0 XML, and
`BpmnCompilationPlan` records how every source item was mapped.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MappingStatus = Literal["direct", "encoded", "visual_annotation", "semantic_payload", "blocked"]

ACTIVITY_NODE_TYPES: frozenset[str] = frozenset(
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


class BPMNDataStore(BaseModel):
    id: str
    name: str
    sourceNodeRef: str | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNTextAnnotation(BaseModel):
    id: str
    text: str
    sourceNodeRef: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)


class BPMNAssociation(BaseModel):
    id: str
    sourceRef: str
    targetRef: str
    direction: Literal["none", "one", "both"] = "none"


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
    dataStores: list[BPMNDataStore] = Field(default_factory=list)
    textAnnotations: list[BPMNTextAnnotation] = Field(default_factory=list)
    associations: list[BPMNAssociation] = Field(default_factory=list)
    model_warnings: list[str] = Field(default_factory=list)
    compilationPlan: BpmnCompilationPlan | None = None
    sourceProcessUnderstanding: dict | None = None
