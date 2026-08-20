from operator import add
from typing import Annotated

from backend.graphs.project.state import ProjectState


class ProjectProcessCoordinationState(ProjectState):
    process_coordination_objective: str | None
    process_readiness_matrix: list[dict]
    cross_process_dependencies: Annotated[list[dict], add]
    process_gaps: Annotated[list[dict], add]
    interview_needs: Annotated[list[dict], add]
    process_workplan: Annotated[list[dict], add]
    recommended_process_focus: str | None
