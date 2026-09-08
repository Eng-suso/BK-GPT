import logging

from backend import workspace_database
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)

logger = logging.getLogger(__name__)


def load_evidence_ledger(project_id: str | None, process_id: str | None) -> dict:
    """Il registro dell'evidenza gia' raccolta su questo processo.

    Senza questo, ogni chat ripartiva dal solo transcript: cio' che una fonte
    aveva gia' detto in un turno precedente tornava a essere "informazione
    mancante" al turno dopo, perche' i claim vivevano solo nello stato del
    giro. Qui l'apertura del turno legge cio' che e' persistito, dentro il
    confine del proprio processo.

    Args:
        project_id: Progetto del turno.
        process_id: Processo del turno.

    Returns:
        Il registro (`status`, `claims`, `summary`), o uno vuoto se il
        canonical non e' configurato o la lettura fallisce: la chat deve poter
        aprirsi anche senza knowledge graph.
    """
    if not project_id or not process_id:
        return {"status": "empty", "claims": [], "count": 0}
    from backend.toolsets.process_memory import process_claim_ledger

    try:
        return process_claim_ledger(project_id, process_id)
    except Exception:  # noqa: BLE001 — l'apertura del turno non deve fallire per questo
        logger.warning(
            "registro evidenza non caricato per il processo %s", process_id, exc_info=True
        )
        return {"status": "error", "claims": [], "count": 0}


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
            "evidence_ledger": {"status": "empty", "claims": [], "count": 0},
        }

    ledger = load_evidence_ledger(process["project_id"], process_id)
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
            "evidence_ledger": ledger,
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
        "evidence_ledger": ledger,
    }
