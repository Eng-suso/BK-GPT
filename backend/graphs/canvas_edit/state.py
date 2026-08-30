from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState
from backend.graphs.canvas_edit.models import (
    CanvasConstructionPlan,
    CanvasPatchPlan,
    CanvasValidationReport,
)
from backend.bpmn_semantic import BPMNSemanticModel
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingDiagnostics,
    ProcessUnderstandingQualityReport,
)


class CanvasState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    bpmn_model_id: str
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding: ProcessUnderstanding | None
    process_understanding_diagnostics: ProcessUnderstandingDiagnostics | None
    process_quality_report: ProcessUnderstandingQualityReport | None
    bpmn_semantic_model: BPMNSemanticModel | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None

    canvas_route: str | None
    canvas_mode: str | None
    canvas_objective: str | None
    goal: str | None
    intent: str | None
    next_action: str | None
    suggested_capability: str | None
    authorized_capability: str | None
    orchestration_status: str | None
    termination_reason: str | None
    blocking_conditions: list[str]
    required_context: list[str]
    reasoning_summary: str | None
    workflow_scope: str | None
    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float
    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict

    patch_plan: CanvasPatchPlan | dict | None
    construction_plan: CanvasConstructionPlan | dict | None
    validation_report: CanvasValidationReport | dict | None
    canvas_layout_report: dict | None
    canvas_layout_status: str | None
    preview_diff: dict | None
    canvas_warnings: list[str]
    canvas_next_actions: list[dict]
    canvas_loop_status: str | None
    canvas_loop_attempt: int
    canvas_loop_max_attempts: int
    canvas_initial_saved_bpmn_xml: str | None
    canvas_last_validation: dict | None
    canvas_task_log: Annotated[list[dict], add]
    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
