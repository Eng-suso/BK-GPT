"""Typed BPMN model — the intermediate representation the compiler produces and
the serializer consumes.

`BPMNSemanticModel` is DeliR's canonical BPMN IR: a `ProcessUnderstanding` is
compiled into one of these, it is validated and serialized to BPMN 2.0 XML, and
`BpmnCompilationPlan` records how every source item was mapped.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

MappingStatus = Literal["direct", "encoded", "visual_annotation", "semantic_payload", "blocked"]

EventDefinitionKind = Literal[
    "timer", "message", "conditional", "signal", "error", "escalation", "terminate",
    "link", "compensation", "cancel", "multiple",
]

# Which event definitions each event may carry (OMG BPMN 2.0, tables 10.84-10.93).
# A start event of an event sub-process may also catch error, escalation and
# compensation; that start sits inside the sub-process, not in the process.
EVENT_DEFINITIONS_BY_NODE_TYPE: dict[str, frozenset[str]] = {
    "startEvent": frozenset({"message", "timer", "conditional", "signal", "multiple", "error", "escalation", "compensation"}),
    "intermediateCatchEvent": frozenset({"message", "timer", "conditional", "link", "signal", "multiple"}),
    "intermediateThrowEvent": frozenset({"message", "escalation", "link", "compensation", "signal", "multiple"}),
    "boundaryEvent": frozenset(
        {"message", "timer", "escalation", "conditional", "error", "cancel", "compensation", "signal", "multiple"}
    ),
    "endEvent": frozenset({"message", "error", "escalation", "cancel", "compensation", "signal", "terminate", "multiple"}),
}
# Triggers that can make up a multiple event: the ones a single event can name.
MULTIPLE_TRIGGERS: frozenset[str] = frozenset({"message", "timer", "conditional", "signal", "escalation", "error", "compensation"})
_CATCH_EVENT_TYPES = frozenset({"startEvent", "intermediateCatchEvent", "boundaryEvent"})

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
        "callActivity",
        "transaction",
        "adHocSubProcess",
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
        "callActivity",
        "transaction",
        "adHocSubProcess",
        "exclusiveGateway",
        "parallelGateway",
        "inclusiveGateway",
        "complexGateway",
        "eventBasedGateway",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "boundaryEvent",
        "subProcess",
    ]
    name: str
    laneId: str | None = None
    owner: str | None = None
    eventDefinition: EventDefinitionKind | None = None
    eventConditionExpression: str | None = None
    # eventDefinition="multiple": the triggers, any one of which fires the event,
    # or every one of them when parallelMultiple (catch events only).
    triggers: list[EventDefinitionKind] = Field(default_factory=list)
    parallelMultiple: bool = False
    # Activity loop marker (OMG BPMN 2.0 10.2.3). Only valid on activity nodes.
    loopCharacteristics: Literal[
        "none", "standardLoop", "multiInstanceSequential", "multiInstanceParallel"
    ] = "none"
    # Boolean expression that keeps a standardLoop iterating.
    loopConditionExpression: str | None = None
    attachedToRef: str | None = None
    cancelActivity: bool = True
    defaultFlowId: str | None = None
    # Complex gateway: when the join fires, e.g. "2 of 3 offers arrived" (OMG 10.5.7).
    activationCondition: str | None = None
    # Event-based gateway that starts the process (no incoming flow); "Parallel"
    # waits for every event, which OMG allows only on an instantiating gateway (10.5.6).
    instantiate: bool = False
    eventGatewayType: Literal["Exclusive", "Parallel"] = "Exclusive"
    # A start event inside an event sub-process may let the process go on
    # (non-interrupting, dashed border).
    isInterrupting: bool = True
    # Activity that undoes a completed one; reached only from a compensation
    # boundary event through an association (OMG BPMN 2.0, 10.6).
    isForCompensation: bool = False
    # callActivity: the process (or global task) it invokes.
    calledElement: str | None = None
    # subProcess run by an event rather than by the flow (an event sub-process):
    # `eventSubProcessStart` is the start event inside it that names the trigger.
    triggeredByEvent: bool = False
    eventSubProcessStart: BPMNFlowNode | None = None
    documentation: str | None = None
    sourceRefs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _markers_match_node_type(self) -> "BPMNFlowNode":
        """Loop markers are activity-only; a terminate definition is endEvent-only.

        Raises:
            ValueError: if a marker is set on an incompatible node type.
        """
        if self.loopCharacteristics != "none" and self.type not in ACTIVITY_NODE_TYPES:
            raise ValueError(
                f"loopCharacteristics is only valid on an activity, not {self.type!r}"
            )
        if self.eventDefinition is not None:
            allowed = EVENT_DEFINITIONS_BY_NODE_TYPE.get(self.type, frozenset())
            if self.eventDefinition not in allowed:
                raise ValueError(f"a {self.eventDefinition} event definition is not valid on a {self.type}")
        if self.eventDefinition == "multiple":
            if len(set(self.triggers)) < 2 or not set(self.triggers) <= MULTIPLE_TRIGGERS:
                raise ValueError("a multiple event needs at least two distinct triggers")
        elif self.triggers:
            raise ValueError("triggers are only valid on a multiple event")
        if self.parallelMultiple and not (self.eventDefinition == "multiple" and self.type in _CATCH_EVENT_TYPES):
            raise ValueError("parallelMultiple is only valid on a multiple catch event")
        if not self.isInterrupting and self.type != "startEvent":
            raise ValueError("isInterrupting is only valid on a start event")
        if self.isForCompensation and self.type not in ACTIVITY_NODE_TYPES:
            raise ValueError("isForCompensation is only valid on an activity")
        if self.calledElement is not None and self.type != "callActivity":
            raise ValueError("calledElement is only valid on a callActivity")
        if self.triggeredByEvent != (self.eventSubProcessStart is not None) or (
            self.triggeredByEvent and self.type != "subProcess"
        ):
            raise ValueError("an event sub-process is a subProcess with the start event that triggers it")
        start = self.eventSubProcessStart
        if start is not None and (start.type != "startEvent" or start.eventDefinition is None):
            raise ValueError("an event sub-process starts from a start event with a trigger")
        if self.activationCondition is not None and self.type != "complexGateway":
            raise ValueError("an activation condition is only valid on a complexGateway")
        if (self.instantiate or self.eventGatewayType != "Exclusive") and self.type != "eventBasedGateway":
            raise ValueError("instantiate and eventGatewayType are only valid on an eventBasedGateway")
        if self.eventGatewayType == "Parallel" and not self.instantiate:
            raise ValueError("a parallel event-based gateway must instantiate the process")
        return self


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
    type: Literal[
        "exclusiveGateway", "parallelGateway", "inclusiveGateway", "complexGateway", "eventBasedGateway"
    ] = "exclusiveGateway"
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
