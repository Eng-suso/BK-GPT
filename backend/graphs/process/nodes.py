from backend import workspace_database


def load_process_context(state: dict) -> dict:
    process_id = state.get("process_id")
    if not process_id:
        return {}

    process = workspace_database.get_process(process_id)
    if process is None:
        return {
            "process_name": None,
            "bpmn_model_id": None,
            "process_understanding_json": None,
            "bpmn_semantic_model_json": None,
            "readiness_score": None,
            "missing_information": [],
            "saved_bpmn_xml": None,
        }

    bpmn_model = workspace_database.get_bpmn_model(process["bpmn_model_id"])
    review = workspace_database.get_bpmn_review(process["bpmn_model_id"])

    if review is None:
        return {
            "process_name": process["name"],
            "bpmn_model_id": process["bpmn_model_id"],
            "process_understanding_json": None,
            "bpmn_semantic_model_json": None,
            "readiness_score": None,
            "missing_information": [],
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        }

    return {
        "process_name": process["name"],
        "bpmn_model_id": process["bpmn_model_id"],
        "process_understanding_json": review.get("process_understanding"),
        "bpmn_semantic_model_json": review.get("bpmn_semantic_model"),
        "readiness_score": review.get("readiness_score"),
        "missing_information": review.get("missing_information") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
    }
