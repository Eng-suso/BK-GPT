import json

from pydantic import BaseModel

from backend.agents.evidence_brief import (
    content_tokens,
    is_catch_all_question,
    question_is_grounded,
)
from backend.bpmn import (
    BPMNSemanticModel,
    build_bpmn_semantic_model,
    semantic_model_to_bpmn_xml,
    validate_bpmn_semantic_model,
)
from backend.process_understanding import (
    ExtractionFailure,
    ProcessUnderstanding,
    ProcessUnderstandingExtractionError,
    ProcessUnderstandingQualityReport,
    ProcessUnderstandingResult,
    build_process_understanding,
    evaluate_process_understanding_quality,
    process_open_questions,
    process_understanding_diagnostics,
    raise_for_failed_understanding,
    readiness_from_understanding,
    render_process_review,
)


class BpmnReviewDraft(BaseModel):
    execution_status: str = "success"
    can_generate_bpmn: bool = True
    extraction_failure: ExtractionFailure | None = None
    source_text: str
    process_understanding: ProcessUnderstanding
    bpmn_semantic_model: BPMNSemanticModel
    bpmn_brief: str
    readiness_score: int
    quality_report: ProcessUnderstandingQualityReport
    missing_information: list[str]

    def process_understanding_json(self) -> str:
        return self.process_understanding.model_dump_json()

    def bpmn_semantic_model_json(self) -> str:
        return self.bpmn_semantic_model.model_dump_json()


def partition_grounded_unknowns(
    process: ProcessUnderstanding, source_text: str
) -> tuple[list, list]:
    """Separa le domande che citano una lacuna reale da quelle che non lo fanno.

    PROCESS-V2-12/15: le domande bloccanti proponevano "sourcing", "verifica
    budget", "conformita'", "soglie di approvazione" - temi di settore, non
    lacune di questo processo. Consegnate al consulente sembrano il risultato
    della discovery e lo portano a descrivere un processo che non e' il suo.

    Il giudizio e' deterministico: una domanda regge se dichiara la lacuna in
    `grounded_in` con parole che nelle note esistono, o se nomina qualcosa delle
    note. Cade solo se, oltre a non agganciarsi, chiede una categoria intera. Le
    note vuote non producono scarti: la prima passata di discovery deve poter
    fare domande larghe.

    Args:
        process: Il ProcessUnderstanding proposto.
        source_text: Le note su cui e' stato estratto.

    Returns:
        `(tenute, scartate)`, nell'ordine originale.
    """
    vocabulary = content_tokens(source_text)
    kept, dropped = [], []
    for unknown in process.unknowns:
        grounded = question_is_grounded(
            unknown.question,
            vocabulary,
            grounded_in=getattr(unknown, "grounded_in", ""),
        )
        (kept if grounded else dropped).append(unknown)
    return kept, dropped


def _ungrounded_question_warning(dropped: list) -> str:
    questions = "; ".join(
        " ".join(str(item.question or "").split())[:120] for item in dropped
    )
    return (
        "Domande di chiarimento scartate perche' non citano una lacuna di questo "
        f"processo: {questions}. Riformulale partendo da cio' che le fonti hanno "
        "gia' detto, oppure estrai quella conoscenza invece di richiederla."
    )


def build_bpmn_review_draft(
    bpmn_process_id: str,
    process_name: str,
    source_text: str,
    process_understanding: ProcessUnderstanding | ProcessUnderstandingResult | dict | None = None,
) -> BpmnReviewDraft:
    process_model: ProcessUnderstanding
    if process_understanding is None:
        process_model = raise_for_failed_understanding(
            build_process_understanding(process_name, source_text)
        )
    elif isinstance(process_understanding, ProcessUnderstandingResult):
        process_model = raise_for_failed_understanding(process_understanding)
    elif isinstance(process_understanding, dict) and "status" in process_understanding:
        process_model = raise_for_failed_understanding(
            ProcessUnderstandingResult.model_validate(process_understanding)
        )
    else:
        process_model = ProcessUnderstanding.model_validate(process_understanding)
    process_model.schema_version = "process_understanding.v1"
    # Le domande passano di qui prima di diventare le "domande del piano" che il
    # consulente legge: e' l'unico punto attraversato sia dall'estrazione LLM sia
    # dal ProcessUnderstanding che l'agente propone gia' strutturato.
    kept_unknowns, ungrounded_unknowns = partition_grounded_unknowns(
        process_model, source_text
    )
    process_model.unknowns = kept_unknowns
    bpmn_semantic_model = build_bpmn_semantic_model(
        process_id=bpmn_process_id,
        process_name=process_name,
        process=process_model,
    )
    _ensure_review_artifacts(process_model, bpmn_semantic_model)
    semantic_warnings = validate_bpmn_semantic_model(bpmn_semantic_model)
    process_model.quality_report = evaluate_process_understanding_quality(
        process_model,
        source_text=source_text,
        bpmn_warnings=semantic_warnings,
    )
    bpmn_semantic_model = build_bpmn_semantic_model(
        process_id=bpmn_process_id,
        process_name=process_name,
        process=process_model,
    )
    missing_information = process_open_questions(process_model)
    diagnostics = process_understanding_diagnostics(process_model)
    missing_information.extend(diagnostics.blocking)
    missing_information.extend(
        warning for warning in semantic_warnings if warning not in missing_information
    )
    if process_model.quality_report is None:
        raise ValueError("Quality report mancante dopo la valutazione ProcessUnderstanding.")
    missing_information.extend(
        issue.message
        for issue in process_model.quality_report.blocking_issues
        if issue.message not in missing_information
    )
    if ungrounded_unknowns:
        # Lo scarto e' visibile: resta nel piano come cosa da sistemare, cosi'
        # l'agente sa che quelle domande non sono passate e perche'. Sparire in
        # silenzio le riproporrebbe identiche al giro dopo.
        missing_information.append(_ungrounded_question_warning(ungrounded_unknowns))

    return BpmnReviewDraft(
        source_text=source_text,
        process_understanding=process_model,
        bpmn_semantic_model=bpmn_semantic_model,
        bpmn_brief=render_process_review(process_model),
        readiness_score=readiness_from_understanding(process_model),
        quality_report=process_model.quality_report,
        missing_information=missing_information,
    )


def bpmn_xml_from_review(
    bpmn_semantic_model_json: str,
) -> str:
    stored_semantic_model = json.loads(bpmn_semantic_model_json or "{}")
    bpmn_semantic_model = _canonical_semantic_model(stored_semantic_model)
    return semantic_model_to_bpmn_xml(bpmn_semantic_model)


def _canonical_semantic_model(value: dict) -> BPMNSemanticModel:
    if not value.get("flowNodes") or not value.get("sequenceFlows"):
        raise ValueError("BPMNSemanticModel canonicale mancante o incompleto.")
    if not value.get("compilationPlan") or not value.get("sourceProcessUnderstanding"):
        raise ValueError("BPMNSemanticModel legacy rifiutato: manca il payload semantico canonicale.")
    return BPMNSemanticModel.model_validate(value)


def _ensure_review_artifacts(
    process_understanding: ProcessUnderstanding,
    bpmn_semantic_model: BPMNSemanticModel,
) -> None:
    if not isinstance(process_understanding, ProcessUnderstanding):
        raise ValueError("ProcessUnderstanding non valido per la review BPMN.")

    if process_understanding.scope and "ProcessUnderstanding non generato" in process_understanding.scope:
        raise ProcessUnderstandingExtractionError(
            ExtractionFailure(
                kind="invalid_structured_output",
                message="Review rifiutata: ProcessUnderstanding placeholder da fallimento tecnico.",
                retryable=False,
                attempt=1,
            )
        )

    if not bpmn_semantic_model.flowNodes or not bpmn_semantic_model.sequenceFlows:
        raise ValueError("BPMNSemanticModel incompleto per la review BPMN.")
