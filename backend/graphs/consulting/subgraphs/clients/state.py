from operator import add
from typing import Annotated

from backend.graphs.consulting.state import ConsultingState


class ClientsState(ConsultingState):
    selected_client_id: str | None
    selected_client_name: str | None
    client_operation: str | None
    duplicate_candidates: Annotated[list[dict], add]
    client_changes: Annotated[list[dict], add]
    client_notes: Annotated[list[dict], add]
