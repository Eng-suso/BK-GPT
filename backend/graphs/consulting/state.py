from operator import add
from typing import Annotated

from backend.graphs.common import ConversationState


class ConsultingState(ConversationState):
    scope_type: str
    scope_key: str

    consulting_route: str
    consulting_mode: str | None
    consulting_objective: str | None

    delegation_target: str | None
    delegation_reason: str | None
    delegation_payload: dict
    routing_confidence: float

    needs_clarification: bool
    clarification_question: str | None
    entity_hints: dict
    workspace_overview_json: dict | None

    routing_trace: Annotated[list[dict], add]
    delegation_events: Annotated[list[dict], add]
    next_actions: Annotated[list[dict], add]
    workspace_risks: Annotated[list[str], add]
