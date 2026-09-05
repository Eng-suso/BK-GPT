from backend import workspace_database
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)


def load_process_context(state: dict) -> dict:
    process_id = state.get("process_id")
    if not process_id:
        return {}

    process = workspace_database.get_process(process_id)
    if process is None:
        return {
            "process_name": None,
            "bpmn_model_id": None,
            "process_understanding": None,
            "process_understanding_diagnostics": None,
            "process_quality_report": None,
            "bpmn_semantic_model": None,
            "readiness_score": None,
            "missing_information": [],
            "saved_bpmn_xml": None,
        }

    bpmn_model = workspace_database.get_bpmn_model(process["bpmn_model_id"])
    review = workspace_database.get_bpmn_review(process["bpmn_model_id"], include_approved=True)

    if review is None:
        return {
            "process_name": process["name"],
            "bpmn_model_id": process["bpmn_model_id"],
            "process_understanding": None,
            "process_understanding_diagnostics": None,
            "process_quality_report": None,
            "bpmn_semantic_model": None,
            "readiness_score": None,
            "missing_information": [],
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        }

    process_understanding, bpmn_semantic_model = canonical_semantic_context(
        review.get("bpmn_semantic_model")
    )

    return {
        "process_name": process["name"],
        "bpmn_model_id": process["bpmn_model_id"],
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
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
    }
