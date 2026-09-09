import hashlib
import json
import logging

from backend import workspace_database
from backend.graphs.common import canonical_semantic_context, validated_model
from backend.process_understanding import (
    ProcessUnderstandingQualityReport,
    draft_readiness_from_understanding,
    process_understanding_diagnostics,
    validation_readiness_from_understanding,
)

logger = logging.getLogger(__name__)


def _source_set_id(sources: list[dict]) -> str:
    """L'identita' del set di fonti, confrontabile fra un turno e l'altro.

    Serve a rendere verificabile l'invariante invece di doverla dedurre: due
    fasi che dichiarano lo stesso `source_set_id` hanno letto le stesse fonti.
    Entra anche nella firma di progresso del loop, cosi' una fonte in piu' conta
    come avanzamento.
    """
    identity = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "project_id": str(item.get("project_id") or ""),
            "process_id": str(item.get("process_id") or ""),
        }
        for item in sources
    ]
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def _empty_evidence_snapshot() -> dict:
    return {
        "status": "empty",
        "source_status": "empty",
        "claim_status": "empty",
        "sources": [],
        "source_ids": [],
        "source_count": 0,
        "source_set_id": _source_set_id([]),
        "claims": [],
        "count": 0,
    }


def _authoritative_process_sources(project_id: str, process_id: str) -> list[dict]:
    """Le fonti del processo, con il loro testo, dal registro operativo.

    Il confine e' lo stesso del gateway: le fonti del processo piu' quelle di
    progetto che non appartengono a nessun processo. L'ordine e' per nome, cosi'
    l'elenco non dipende dall'ordine di scrittura. Se il testo di una fonte non
    si carica, la fonte resta comunque nel set: manca il transcript, non
    l'intervista.
    """
    from backend.workspace_services import source_document as source_documents

    records = [
        item
        for item in workspace_database.list_project_sources(project_id)
        if item.get("process_id") in {None, process_id}
    ]
    sources: list[dict] = []
    for record in sorted(
        records,
        key=lambda item: (
            str(item.get("name") or "").casefold(),
            str(item.get("id") or ""),
        ),
    ):
        try:
            document = source_documents.source_document(str(record.get("id") or "")) or {}
        except Exception:  # noqa: BLE001 - the manifest remains authoritative
            logger.warning(
                "testo fonte %s non caricato per il processo %s",
                record.get("id"),
                process_id,
                exc_info=True,
            )
            document = {}
        sources.append(
            {
                **record,
                "summary": str(document.get("summary") or record.get("meta") or "").strip(),
                "participants": list(document.get("participants") or []),
                "content": str(document.get("content") or "").strip(),
                "has_content": bool(document.get("has_content")),
                "episode_id": document.get("episode_id"),
            }
        )
    return sources


def load_evidence_ledger(
    project_id: str | None,
    process_id: str | None,
    *,
    previous: dict | None = None,
) -> dict:
    """Un solo snapshot dell'evidenza, per tutti i consumatori del turno.

    Il set di fonti autoritativo e' il registro operativo del workspace; i claim
    del canonical sono una proiezione, e servono per provenance e corroborazione.
    Prima erano la stessa cosa, e siccome l'ingestione del knowledge graph e'
    asincrona e puo' degradare, "proiezione non pronta" diventava "zero
    interviste": nella stessa chat il consulente vedeva tre fonti, poi nessuna,
    poi di nuovo tre. Qui i due piani restano distinti e ognuno porta il proprio
    stato, cosi' chi legge sa se una fonte manca o se non e' stata letta.

    Args:
        project_id: Progetto del turno.
        process_id: Processo del turno.
        previous: Lo snapshot del turno precedente, se c'e'. Serve solo quando
            la lettura operativa fallisce: meglio l'ultimo set noto, dichiarato
            `stale`, che un vuoto indistinguibile da un processo senza fonti.

    Returns:
        Lo snapshot: fonti con il loro testo, claim proiettati, e gli stati
        separati di ciascun piano.
    """
    if not project_id or not process_id:
        return _empty_evidence_snapshot()

    from backend.toolsets.process_memory import process_claim_ledger

    source_status = "ok"
    try:
        sources = _authoritative_process_sources(project_id, process_id)
    except Exception:  # noqa: BLE001 — non leggibile e vuoto non sono lo stesso stato
        logger.warning(
            "registro fonti non caricato per il processo %s", process_id, exc_info=True
        )
        sources = list((previous or {}).get("sources") or [])
        source_status = "stale" if sources else "error"

    try:
        projected = process_claim_ledger(project_id, process_id)
    except Exception:  # noqa: BLE001 — le fonti restano leggibili comunque
        logger.warning(
            "registro claim non caricato per il processo %s", process_id, exc_info=True
        )
        projected = {"status": "error", "claims": [], "count": 0}

    source_ids = [str(item.get("id") or "") for item in sources if item.get("id")]
    claim_status = str(projected.get("status") or "empty")
    status = source_status if source_status != "ok" else ("ok" if sources else "empty")
    return {
        **projected,
        "status": status,
        "source_status": source_status,
        "claim_status": claim_status,
        "sources": sources,
        "source_ids": source_ids,
        "source_count": len(sources),
        "source_set_id": _source_set_id(sources),
        "claims": list(projected.get("claims") or []),
        "count": len(projected.get("claims") or []),
    }


def evidence_count(snapshot: dict) -> int:
    """Quanta evidenza questo processo ha davvero agli atti.

    Le fonti salvate e i claim proiettati non arrivano insieme: l'ingestione del
    knowledge graph e' asincrona, quindi fra il salvataggio di un'intervista e la
    sua proiezione esiste una finestra in cui i claim sono zero e le fonti no.
    Contare i soli claim in quella finestra fa dire "nessuna evidenza" a un
    processo che ha tre interviste sul tavolo.

    Args:
        snapshot: Lo snapshot di `load_evidence_ledger`.

    Returns:
        Il numero di elementi di evidenza registrati, fonti o claim che siano.
    """
    return max(
        int(snapshot.get("source_count") or 0),
        len(snapshot.get("claims") or []),
    )


def load_process_context(state: dict) -> dict:
    """Lo stato del processo con cui si apre ogni turno.

    Il nodo riapre a ogni giro del loop, quindi cio' che scrive vince su cio'
    che i tool hanno scritto prima: readiness e registro dell'evidenza si
    ricavano qui dallo stato persistito, non si leggono da un campo che qualcuno
    potrebbe aver lasciato indietro.

    Args:
        state: Lo stato del turno, non affidabile. Serve `process_id`; se c'e'
            gia' uno snapshot dell'evidenza viene usato solo come ultima
            risorsa, quando la lettura fallisce.

    Returns:
        Processo, review, BPMN salvato, le due readiness e lo snapshot
        dell'evidenza. Vuoto se il turno non e' su un processo.

    Sola lettura.
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
            "draft_readiness": None,
            "validation_readiness": None,
            "missing_information": [],
            "review_open_questions": [],
            "saved_bpmn_xml": None,
            "evidence_ledger": _empty_evidence_snapshot(),
        }

    ledger = load_evidence_ledger(
        process["project_id"], process_id, previous=state.get("evidence_ledger")
    )
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
            "draft_readiness": None,
            "validation_readiness": None,
            "missing_information": [],
            "review_open_questions": [],
            "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
            "evidence_ledger": ledger,
        }

    process_understanding, bpmn_semantic_model = canonical_semantic_context(
        review.get("bpmn_semantic_model")
    )
    # Le due soglie si ricavano qui dallo stesso ProcessUnderstanding salvato,
    # non da un campo persistito: questo nodo riapre a ogni giro del loop, e un
    # valore letto da altrove sovrascriverebbe quello appena calcolato dal tool
    # di modeling. Derivarlo significa che lo stesso processo, dopo un restart o
    # un checkpoint, torna alla stessa readiness.
    draft_readiness = (
        draft_readiness_from_understanding(process_understanding)
        if process_understanding
        else None
    )
    validation_readiness = (
        validation_readiness_from_understanding(process_understanding)
        if process_understanding
        else None
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
        "draft_readiness": draft_readiness,
        "validation_readiness": validation_readiness,
        "missing_information": review.get("missing_information") or [],
        "review_open_questions": review.get("open_questions") or [],
        "saved_bpmn_xml": bpmn_model["xml"] if bpmn_model else None,
        "evidence_ledger": ledger,
    }
