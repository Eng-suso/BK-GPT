from backend.graphs.common import ConversationState


class ConsultingState(ConversationState):
    scope_type: str
    scope_key: str
