from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState


class ProcessState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    process_name: str | None
    bpmn_model_id: str | None
    process_understanding_json: dict | str | None
    bpmn_semantic_model_json: dict | str | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None

    process_route: str | None
    process_mode: str | None
    process_objective: str | None
    process_phase: str | None
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
    engineering_loop_iteration: int
    engineering_loop_max_iterations: int
    process_no_progress_count: int
    process_progress_signature: str | None
    process_continue_loop: bool
    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float
    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict

    discovery_readiness: dict | None
    evidence_coverage: dict | None
    canvas_handoff_payload: dict | None

    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
    process_claims: Annotated[list[dict], add]
    process_gaps: Annotated[list[dict], add]
    contradictions: Annotated[list[dict], add]
    assumptions: Annotated[list[str], add]
    modeling_warnings: Annotated[list[str], add]
    process_next_actions: Annotated[list[dict], add]
