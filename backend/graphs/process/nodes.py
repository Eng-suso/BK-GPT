from backend import workspace_database
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)


def load_process_context(state: dict) -> dict:
    """Load process metadata, review results, and saved BPMN content for the requested process.
    
    Args:
        state (dict): Untrusted state containing the optional ``process_id`` used to
            identify the process.
    
    Returns:
        dict: A normalized process context. Returns an empty dictionary when no
        process ID is provided. For an unknown process, returns a context with
        null process data, empty review lists, and no saved BPMN XML. Existing
        contexts include process metadata, saved BPMN XML, semantic-model data,
        diagnostics, quality data, readiness, and review findings, with missing
        list values normalized to empty lists.
    
    Raises:
        KeyError: If a retrieved process lacks a required process field.
        TypeError: If stored review data cannot be processed by the semantic-model
            or quality-report validators.
    
    Side Effects:
        Performs read-only database lookups and does not persist changes.
    """
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
            "review_open_questions": [],
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
            "review_open_questions": [],
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
        "review_open_questions": review.get("open_questions") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
    }
