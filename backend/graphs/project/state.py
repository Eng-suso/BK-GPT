from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState


class ProjectState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str

    project_name: str | None
    client_id: str | None
    client_name: str | None
    project_phase: str | None
    project_status: str | None
    progress: int | None
    next_step: str | None
    project_processes: list[dict]
    project_sources: list[dict]
    project_decisions: list[dict]
    project_deliverables: list[str]
    project_open_issues: list[str]

    project_route: str | None
    project_mode: str | None
    project_objective: str | None
    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float
    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict

    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
    project_next_actions: Annotated[list[dict], add]
    project_risks: Annotated[list[dict], add]
