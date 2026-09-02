from backend import workspace_database
from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)


def _validated_model(model_cls, value):
    if not value:
        return None

    try:
        return model_cls.model_validate(value)
    except Exception:
        return None


def _canonical_semantic_context(
    review: dict | None,
) -> tuple[ProcessUnderstanding | None, BPMNSemanticModel | None]:
    if not review:
        return None, None

    semantic_model = _validated_model(BPMNSemanticModel, review.get("bpmn_semantic_model"))
    if not semantic_model:
        return None, None
    if not semantic_model.compilationPlan or not semantic_model.sourceProcessUnderstanding:
        return None, None

    understanding = _validated_model(
        ProcessUnderstanding,
        semantic_model.sourceProcessUnderstanding,
    )
    return understanding, semantic_model


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
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
            "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
            "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
        }

    process_understanding, bpmn_semantic_model = _canonical_semantic_context(review)

    return {
        "process_name": process["name"] if process else None,
        "process_understanding": process_understanding,
        "process_understanding_diagnostics": process_understanding_diagnostics(
            process_understanding
        )
        if process_understanding
        else None,
        "process_quality_report": _validated_model(
            ProcessUnderstandingQualityReport,
            review.get("quality_report"),
        ),
        "bpmn_semantic_model": bpmn_semantic_model,
        "readiness_score": review.get("readiness_score"),
        "missing_information": review.get("missing_information") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        "effective_bpmn_xml": live_xml or (bpmn_model["xml"] if bpmn_model else None),
        "effective_bpmn_xml_source": "live_canvas" if live_xml else "saved_backend",
    }
