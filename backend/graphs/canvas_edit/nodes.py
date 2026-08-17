from backend import workspace_database


def load_canvas_context(state: dict) -> dict:
    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {}

    bpmn_model = workspace_database.get_bpmn_model(bpmn_model_id)
    review = workspace_database.get_bpmn_review(bpmn_model_id)
    process = workspace_database.get_process(bpmn_model["process_id"]) if bpmn_model else None
    live_xml = state.get("current_bpmn_xml")

    if review is None:
        return {
            "process_name": process["name"] if process else None,
            "process_understanding_json": None,
            "bpmn_semantic_model_json": None,
            "readiness_score": None,
            "missing_information": [],
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
            "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
            "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
        }

    return {
        "process_name": process["name"] if process else None,
        "process_understanding_json": review.get("process_understanding"),
        "bpmn_semantic_model_json": review.get("bpmn_semantic_model"),
        "readiness_score": review.get("readiness_score"),
        "missing_information": review.get("missing_information") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
        "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
    }
