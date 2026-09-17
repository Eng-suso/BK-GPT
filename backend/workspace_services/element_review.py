"""Il consulente rivede un elemento che nessuna fonte regge: lo conferma o lo toglie.

Il rapporto di provenance segna le inferenze; il disegno le mostra. Senza un modo
di chiuderle, un canvas con tre passaggi "da confermare" resta con tre passaggi
da confermare per sempre, e il segno perde significato. Qui la revisione ha due
esiti, e sono due operazioni diverse:

| decisione | cosa cambia |
| --- | --- |
| `confirmed` | il piano no: l'elemento era giusto, solo che nessuno lo aveva detto nelle interviste. Si registra chi lo conferma e si aggiorna il segno sul canvas **salvato** - senza ridisegnarlo, cosi' le modifiche a mano restano |
| `rejected` | il piano si': l'elemento esce, il flusso intorno si ricuce, la review sale di versione e il disegno si rigenera dal piano nuovo |

Il rifiuto vale per passaggi, eventi ed eccezioni. Togliere un attore o una
decisione cambia la struttura del processo e si corregge sul piano, non con un
click: rifiutarlo qui lascerebbe corsie vuote o rami senza origine.

Ogni scrittura si rilegge, come nel resto del confine.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

from backend.agents.plan_element_removal import (
    REMOVABLE_KINDS,
    ElementNotRemovable,
    remove_plan_element,
)
from backend.agents.plan_provenance import ElementProvenance, ProvenanceReport
from backend.agents.process_snapshot import ProcessKnowledgeSnapshot, build_process_snapshot
from backend.workspace_services.bpmn_draft import BpmnDraftResult, generate_bpmn_draft
from backend.workspace_services.bpmn_provenance_marks import mark_provenance
from backend.workspace_services.write_verification import (
    PersistenceVerificationError,
    verify_bpmn_model_persisted,
    verify_review_persisted,
)

logger = logging.getLogger(__name__)

ReviewReasonCode = Literal[
    "reviewed",
    "process_not_found",
    "no_plan",
    "element_not_found",
    "not_removable",
    "plan_revision_failed",
    "marks_refresh_failed",
    "redraw_failed",
]


@dataclass(frozen=True)
class ElementReviewResult:
    """L'esito di una revisione, con il rapporto riletto dopo la scrittura."""

    ok: bool
    reason_code: ReviewReasonCode
    reason: str
    snapshot: ProcessKnowledgeSnapshot | None
    draft: BpmnDraftResult | None = None

    @property
    def provenance(self) -> ProvenanceReport | None:
        return self.snapshot.provenance if self.snapshot else None


def _find(report: ProvenanceReport | None, source_ref: str) -> ElementProvenance | None:
    if report is None:
        return None
    return next((item for item in report.elements if item.source_ref == source_ref), None)


def _refresh_marks(snapshot: ProcessKnowledgeSnapshot) -> str | None:
    """Aggiorna i segni di provenance sul canvas salvato, senza ridisegnarlo.

    Returns:
        La ragione del guasto, o `None` se il canvas e' stato aggiornato e
        riletto (o non c'era un canvas da aggiornare).
    """
    from backend import workspace_database

    if snapshot.provenance is None:
        return None
    model = workspace_database.get_bpmn_model(snapshot.bpmn_model_id)
    xml = str((model or {}).get("xml") or "")
    if not xml.strip():
        return None
    try:
        marked, _counts = mark_provenance(xml, snapshot.provenance.status_by_source_ref())
    except (ET.ParseError, ValueError, TypeError) as exc:
        return f"Il canvas salvato non e' leggibile: {exc}"
    if marked == xml:
        return None
    try:
        workspace_database.update_bpmn_model(
            snapshot.bpmn_model_id,
            marked,
            change_summary="Revisione evidenze: elemento confermato dal consulente",
            source="provenance_review",
        )
        verify_bpmn_model_persisted(snapshot.bpmn_model_id, marked)
    except PersistenceVerificationError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - un guasto di scrittura si racconta, non si nasconde
        logger.warning(
            "aggiornamento segni provenance fallito per %s", snapshot.process_id, exc_info=True
        )
        return f"{type(exc).__name__}: {exc}"
    return None


def review_plan_element(
    process_id: str,
    *,
    source_ref: str,
    decision: Literal["confirmed", "rejected"],
    note: str = "",
) -> ElementReviewResult:
    """Applica la decisione del consulente su un elemento del piano.

    Args:
        process_id: Il processo, non affidabile.
        source_ref: Il riferimento di tracciabilita' dell'elemento, dal rapporto.
        decision: `confirmed` o `rejected`.
        note: Perche', se il consulente lo scrive.

    Returns:
        L'esito, con lo snapshot riletto dopo la scrittura e - per un rifiuto -
        l'esito del ridisegno.

    Side effects:
        Scrive la decisione sulla review. Una conferma aggiorna i segni sul
        canvas salvato; un rifiuto scrive una nuova versione del piano e rigenera
        il canvas.
    """
    from backend import workspace_database

    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        return ElementReviewResult(
            ok=False,
            reason_code="process_not_found",
            reason=f"Processo non trovato: {process_id}",
            snapshot=None,
        )
    if snapshot.provenance is None or not snapshot.process_understanding:
        return ElementReviewResult(
            ok=False,
            reason_code="no_plan",
            reason="Questo processo non ha un piano da rivedere.",
            snapshot=snapshot,
        )

    element = _find(snapshot.provenance, source_ref)
    if element is None:
        return ElementReviewResult(
            ok=False,
            reason_code="element_not_found",
            reason=(
                "L'elemento non e' nel piano corrente: il piano puo' essere cambiato "
                "mentre lo stavi rivedendo."
            ),
            snapshot=snapshot,
        )

    if decision == "confirmed":
        workspace_database.record_element_decision(
            snapshot.bpmn_model_id,
            source_ref=source_ref,
            label=element.label,
            decision="confirmed",
            note=note,
        )
        refreshed = build_process_snapshot(process_id)
        failure = _refresh_marks(refreshed) if refreshed else None
        if failure:
            # La decisione e' registrata - e' la parte che conta - ma il disegno
            # non la mostra ancora: dirlo invece di dichiarare tutto fatto.
            return ElementReviewResult(
                ok=False,
                reason_code="marks_refresh_failed",
                reason=(
                    "Conferma registrata, ma il canvas salvato non e' stato aggiornato: "
                    f"{failure}"
                ),
                snapshot=refreshed,
            )
        return ElementReviewResult(
            ok=True,
            reason_code="reviewed",
            reason=f"«{element.label}» confermato.",
            snapshot=refreshed,
        )

    if element.kind not in REMOVABLE_KINDS:
        return ElementReviewResult(
            ok=False,
            reason_code="not_removable",
            reason=(
                f"«{element.label}» non si toglie dalla revisione delle evidenze: "
                "cambia la struttura del processo e va corretto sul piano."
            ),
            snapshot=snapshot,
        )

    previous_version = snapshot.version
    try:
        revised = remove_plan_element(
            snapshot.process_understanding, kind=element.kind, element_id=element.element_id
        )
        workspace_database.revise_bpmn_review(
            bpmn_model_id=snapshot.bpmn_model_id,
            process_understanding=revised.model_dump(mode="json"),
            change_summary=f"Revisione evidenze: rifiutato «{element.label}»",
        )
        verify_review_persisted(
            snapshot.bpmn_model_id,
            expect_plan_content=True,
            minimum_version=previous_version + 1,
        )
    except (ElementNotRemovable, PersistenceVerificationError, ValueError) as exc:
        logger.warning("rifiuto elemento non applicato per %s", process_id, exc_info=True)
        return ElementReviewResult(
            ok=False,
            reason_code="plan_revision_failed",
            reason=f"Il piano non e' stato aggiornato: {exc}",
            snapshot=build_process_snapshot(process_id),
        )

    workspace_database.record_element_decision(
        snapshot.bpmn_model_id,
        source_ref=source_ref,
        label=element.label,
        decision="rejected",
        note=note,
    )

    draft = generate_bpmn_draft(
        process_id,
        change_summary=f"Revisione evidenze: rifiutato «{element.label}»",
        source="provenance_review",
        synthesize_missing_plan=False,
    )
    after = build_process_snapshot(process_id)
    if not draft.ok:
        return ElementReviewResult(
            ok=False,
            reason_code="redraw_failed",
            reason=(
                f"«{element.label}» e' stato tolto dal piano, ma il disegno non e' stato "
                f"rigenerato: {draft.reason}"
            ),
            snapshot=after,
            draft=draft,
        )
    return ElementReviewResult(
        ok=True,
        reason_code="reviewed",
        reason=f"«{element.label}» tolto dal piano e dal disegno.",
        snapshot=after,
        draft=draft,
    )
