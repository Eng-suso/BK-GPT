from operator import add
from typing import Annotated

from backend.graphs.process.state import ProcessState


class ProcessModelingState(ProcessState):
    process_understanding_review: dict | None
    semantic_model_validation: dict | None
    modeling_next_steps: Annotated[list[dict], add]
