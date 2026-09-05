from backend import workspace_database
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)


def load_canvas_context(state: dict) -> dict:
    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {}

    bpmn_model = workspace_database.get_bpmn_model(bpmn_model_id)
    review = workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)
    process = workspace_database.get_process(bpmn_model["process_id"]) if bpmn_model else None
    live_xml = state.get("current_bpmn_xml")

    if review is None:
        return {
            "process_name": process["name"] if process else None,
            "process_understanding": None,
            "process_understanding_diagnostics": None,
            "process_quality_report": None,
            "bpmn_semantic_model": None,
            "readiness_score": None,
            "missing_information": [],
            "review_open_questions": [],
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
            "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
            "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
        }

    process_understanding, bpmn_semantic_model = canonical_semantic_context(
        review.get("bpmn_semantic_model")
    )

    return {
        "process_name": process["name"] if process else None,
        "process_understanding": process_understanding,
        "process_understanding_diagnostics": process_understanding_diagnostics(
            process_understanding
        )
        if process_understanding
        else None,
        "process_quality_report": validated_model(
            ProcessUnderstandingQualityReport,
            review.get("quality_report"),
        ),
        "bpmn_semantic_model": bpmn_semantic_model,
        "readiness_score": review.get("readiness_score"),
        "missing_information": review.get("missing_information") or [],
        "review_open_questions": review.get("open_questions") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
        "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
    }
