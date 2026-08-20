from operator import add
from typing import Annotated

from backend.graphs.project.state import ProjectState


class ProjectDeliveryState(ProjectState):
    delivery_objective: str | None
    delivery_risks: Annotated[list[dict], add]
    delivery_next_actions: Annotated[list[dict], add]
    milestone_updates: Annotated[list[dict], add]
    deliverable_plan: Annotated[list[dict], add]
