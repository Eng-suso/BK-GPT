"""DeliR BPMN package.

Knowledge Model (`ProcessUnderstanding`) -> compiled IR (`BPMNSemanticModel`)
-> BPMN 2.0 XML + diagram interchange, with a traceability plan and structural
validation alongside.

- `models`           typed BPMN IR
- `topology`         pure pool/lane/message-flow reconciliation
- `compiler`         ProcessUnderstanding -> BPMNSemanticModel
- `serializer`       BPMNSemanticModel -> BPMN XML + DI
- `validation`       structural well-formedness checks
- `compilation_plan` source-item traceability
"""

from backend.bpmn.compilation_plan import build_bpmn_compilation_plan
from backend.bpmn.compiler import build_bpmn_semantic_model
from backend.bpmn.models import (
    ACTIVITY_NODE_TYPES,
    ActivitySpec,
    AnnotationSpec,
    BPMNAssociation,
    BpmnCompilationPlan,
    BPMNDataObject,
    BPMNDataStore,
    BPMNFlowNode,
    BPMNLane,
    BPMNMessageFlow,
    BPMNParticipant,
    BPMNSemanticModel,
    BPMNSequenceFlow,
    BPMNTextAnnotation,
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
from backend.bpmn.serializer import semantic_model_to_bpmn_xml
from backend.bpmn.topology import (
    PoolTopology,
    ResolvedLane,
    ResolvedMessageFlow,
    ResolvedPool,
    resolve_pool_topology,
)
from backend.bpmn.validation import validate_bpmn_semantic_model

__all__ = [
    "ACTIVITY_NODE_TYPES",
    "ActivitySpec",
    "AnnotationSpec",
    "BPMNAssociation",
    "BPMNDataObject",
    "BPMNDataStore",
    "BPMNFlowNode",
    "BPMNLane",
    "BPMNMessageFlow",
    "BPMNParticipant",
    "BPMNSemanticModel",
    "BPMNSequenceFlow",
    "BPMNTextAnnotation",
    "BpmnCompilationPlan",
    "BusinessRuleSpec",
    "CompilationCoverageReport",
    "DataObjectSpec",
    "EventSpec",
    "ExceptionPathSpec",
    "FlowSpec",
    "GatewaySpec",
    "HandoffSpec",
    "LaneSpec",
    "LoopSpec",
    "MappingStatus",
    "ParticipantSpec",
    "PoolTopology",
    "ProcessUnderstandingRef",
    "ResolvedLane",
    "ResolvedMessageFlow",
    "ResolvedPool",
    "TraceabilityLink",
    "build_bpmn_compilation_plan",
    "build_bpmn_semantic_model",
    "resolve_pool_topology",
    "semantic_model_to_bpmn_xml",
    "validate_bpmn_semantic_model",
]
