from operator import add
from typing import Annotated

from backend.graphs.process.state import ProcessState


class ProcessEvidenceState(ProcessState):
    source_list: Annotated[list[dict], add]
    claim_synthesis: Annotated[list[dict], add]
    evidence_open_questions: Annotated[list[str], add]
