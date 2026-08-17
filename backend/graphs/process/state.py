from backend.graphs.common import ConversationState


class ProcessState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    process_name: str | None
    bpmn_model_id: str | None
    process_understanding_json: dict | str | None
    bpmn_semantic_model_json: dict | str | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
