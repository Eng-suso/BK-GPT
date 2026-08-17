import json

from backend.bpmn_semantic import (
    BPMNSemanticModel,
    build_bpmn_semantic_model,
    semantic_model_to_bpmn_xml,
    validate_bpmn_semantic_model,
)
from backend.process_understanding import (
    ProcessUnderstanding,
    build_process_understanding,
    process_open_questions,
    readiness_from_understanding,
    render_process_review,
)


def build_bpmn_review_fields(
    bpmn_process_id: str,
    process_name: str,
    source_text: str,
) -> dict:
    process_understanding = build_process_understanding(process_name, source_text)
    process_understanding.schema_version = "process_understanding.v1"
    bpmn_semantic_model = build_bpmn_semantic_model(
        process_id=bpmn_process_id,
        process_name=process_name,
        process=process_understanding,
    )
    _ensure_review_artifacts(process_understanding, bpmn_semantic_model)
    semantic_warnings = validate_bpmn_semantic_model(bpmn_semantic_model)
    missing_information = process_open_questions(process_understanding)
    missing_information.extend(
        warning for warning in semantic_warnings if warning not in missing_information
    )

    return {
        "source_text": source_text,
        "process_understanding_json": json.dumps(
            process_understanding.model_dump(mode="json"),
            ensure_ascii=False,
        ),
        "bpmn_semantic_model_json": json.dumps(
            bpmn_semantic_model.model_dump(mode="json"),
            ensure_ascii=False,
        ),
        "bpmn_brief": render_process_review(process_understanding),
        "readiness_score": readiness_from_understanding(process_understanding),
        "missing_information": missing_information,
    }


def bpmn_xml_from_review(
    bpmn_process_id: str,
    process_name: str,
    source_text: str,
    process_understanding_json: str,
    bpmn_semantic_model_json: str,
) -> str:
    stored_semantic_model = json.loads(bpmn_semantic_model_json or "{}")

    if stored_semantic_model.get("flowNodes") and stored_semantic_model.get("sequenceFlows"):
        bpmn_semantic_model = BPMNSemanticModel.model_validate(stored_semantic_model)
    else:
        process_understanding = _process_understanding_from_review(
            process_name=process_name,
            source_text=source_text,
            process_understanding_json=process_understanding_json,
        )
        bpmn_semantic_model = build_bpmn_semantic_model(
            process_id=bpmn_process_id,
            process_name=process_name,
            process=process_understanding,
        )

    return semantic_model_to_bpmn_xml(bpmn_semantic_model)


def _process_understanding_from_review(
    process_name: str,
    source_text: str,
    process_understanding_json: str,
) -> ProcessUnderstanding:
    stored_understanding = json.loads(process_understanding_json or "{}")

    if stored_understanding.get("schema_version") == "process_understanding.v1":
        return ProcessUnderstanding.model_validate(stored_understanding)

    return build_process_understanding(process_name, source_text)


def _ensure_review_artifacts(
    process_understanding: ProcessUnderstanding,
    bpmn_semantic_model: BPMNSemanticModel,
) -> None:
    if not isinstance(process_understanding, ProcessUnderstanding):
        raise ValueError("ProcessUnderstanding non valido per la review BPMN.")

    if not bpmn_semantic_model.flowNodes or not bpmn_semantic_model.sequenceFlows:
        raise ValueError("BPMNSemanticModel incompleto per la review BPMN.")
