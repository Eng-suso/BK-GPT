from backend.graphs.common import ConversationState


class ProjectState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
