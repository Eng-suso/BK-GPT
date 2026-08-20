from operator import add
from typing import Annotated

from backend.graphs.consulting.state import ConsultingState


class SetupState(ConsultingState):
    setup_goal: str | None
    setup_plan: Annotated[list[dict], add]
    created_records: Annotated[list[dict], add]
    skipped_records: Annotated[list[dict], add]
    setup_open_questions: Annotated[list[str], add]
