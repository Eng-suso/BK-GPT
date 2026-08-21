from operator import add
from typing import Annotated

from backend.graphs.process.state import ProcessState


class ProcessDiscoveryState(ProcessState):
    discovery_facts: Annotated[list[dict], add]
    discovery_hypotheses: Annotated[list[dict], add]
    discovery_sources_needed: Annotated[list[dict], add]
