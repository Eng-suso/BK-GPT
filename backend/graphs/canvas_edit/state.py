from backend.graphs.common import ConversationState


class CanvasState(ConversationState):
    scope_type: str
    scope_key: str
    project_id: str
    process_id: str
    bpmn_model_id: str
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding_json: dict | str | None
    bpmn_semantic_model_json: dict | str | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None
