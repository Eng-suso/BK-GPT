from operator import add
from typing import Annotated

from backend.graphs.consulting.state import ConsultingState


class HomeState(ConsultingState):
    dashboard_summary: str | None
    priority_items: Annotated[list[dict], add]
    risk_items: Annotated[list[dict], add]
    next_action_items: Annotated[list[dict], add]
    stale_items: Annotated[list[dict], add]
