from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState
from backend.graphs.canvas_edit.models import (
    CanvasConstructionPlan,
    CanvasPatchPlan,
    CanvasValidationReport,
)
from backend.bpmn_semantic import BPMNSemanticModel
from backend.process_understanding import ProcessUnderstanding


class CanvasState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    bpmn_model_id: str
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding_json: dict | str | None
    bpmn_semantic_model_json: dict | str | None
    process_understanding: ProcessUnderstanding | dict | None
    bpmn_semantic_model: BPMNSemanticModel | dict | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None

    canvas_route: str | None
    canvas_mode: str | None
    canvas_objective: str | None
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
    preview_diff: dict | None
    canvas_warnings: list[str]
    canvas_next_actions: list[dict]
    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
