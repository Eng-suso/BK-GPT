import logging

from pydantic import ValidationError

from backend import workspace_database
from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)

logger = logging.getLogger(__name__)


def _validated_model(model_cls, value):
    if not value:
        return None

    try:
        return model_cls.model_validate(value)
    except ValidationError as exc:
        logger.warning(
            "process node: stored %s payload failed validation: %s",
            model_cls.__name__,
            exc,
        )
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

    process_understanding, bpmn_semantic_model = _canonical_semantic_context(review)

    return {
        "process_name": process["name"],
        "bpmn_model_id": process["bpmn_model_id"],
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
    }
