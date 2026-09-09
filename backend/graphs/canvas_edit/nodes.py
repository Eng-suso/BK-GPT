from backend import workspace_database
from backend.agents.process_snapshot import build_process_snapshot
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    process_understanding_diagnostics,
)


def _process_snapshot_context(process_id: str | None, state: dict) -> dict:
    """Lo stato di conoscenza del processo, per il run del canvas.

    Il canvas apriva il turno leggendo la sola review, cioe' il modello
    semantico e le sue lacune: le fonti, i claim con la loro provenance e le
    decisioni gia' prese dal consulente restavano dall'altra parte del confine.
    Con le stesse tre interviste sul tavolo, la Process Chat sapeva chi aveva
    detto cosa e il planner del canvas sapeva un titolo.

    Il run si segna anche su quale versione e' partito (`canvas_run_snapshot_id`):
    e' cio' che rende verificabile "questo disegno viene da V17" e permette di
    accorgersi, a fine giro, che nel frattempo V18 esiste.

    Sola lettura.
    """
    if not process_id:
        return {
            "process_snapshot": None,
            "process_snapshot_id": None,
            "process_snapshot_label": None,
        }

    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        return {
            "process_snapshot": None,
            "process_snapshot_id": None,
            "process_snapshot_label": None,
        }

    context = {
        "process_snapshot": snapshot.model_dump(mode="json"),
        "process_snapshot_id": snapshot.snapshot_id,
        "process_snapshot_label": snapshot.label,
    }
    # La versione di partenza si fissa una volta per run: riscriverla a ogni
    # ricarica renderebbe il confronto finale sempre vero, cioe' inutile.
    if not state.get("canvas_run_snapshot_id"):
        context["canvas_run_snapshot_id"] = snapshot.snapshot_id
    return context


def load_canvas_context(state: dict) -> dict:
    """
    Load BPMN canvas data and review context from workspace storage.

    Args:
        state (dict): Untrusted runtime state containing the BPMN model identifier and
            optional live canvas XML.

    Returns:
        dict: A normalized context containing process metadata, semantic models,
            quality and diagnostic data, review information, the versioned process
            knowledge snapshot, saved XML, effective XML, and its source. Returns an
            empty dictionary when no BPMN model identifier is present. Missing review
            data is represented by null values or empty lists, and effective XML
            prefers live canvas content over saved backend content.

    Side Effects:
        Reads from workspace storage but does not modify or persist data.
    """
    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {}

    bpmn_model = workspace_database.get_bpmn_model(bpmn_model_id)
    review = workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)
    process_id = bpmn_model["process_id"] if bpmn_model else state.get("process_id")
    process = workspace_database.get_process(process_id) if process_id else None
    live_xml = state.get("current_bpmn_xml")
    snapshot_context = _process_snapshot_context(process_id, state)

    if review is None:
        return {
            **snapshot_context,
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
        **snapshot_context,
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
