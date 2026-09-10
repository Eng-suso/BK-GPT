"""Da cio' che le fonti hanno detto a un piano che si puo' disegnare.

Il difetto che questo modulo chiude non era nel Canvas. Con tre interviste agli
atti, lo stato reale del processo era questo:

    fonti: 3   claim: 0   modello semantico: assente   modelable: no

Il piano del processo - la `ProcessUnderstanding` - vive dentro la review BPMN, e
la review esiste solo se qualcuno la prepara. Preparare la review era un passo
dell'agente: il router doveva scegliere `modeling`, il subagente doveva chiamare
`prepare_process_understanding_review` e doveva riempirne bene l'argomento. Tre
condizioni, tutte affidate a un prompt, per un'invariante che invece e' dura:
**se il processo ha evidenza agli atti, il processo ha un piano.**

Quando quel passo non avveniva, il gate del canvas rifiutava per prerequisito
mancante e il turno finiva in chiarimento. Da li' venivano, tutti insieme,
"nessuna intervista disponibile", "nessun attore", il modello start -> end e le
domande da questionario su trigger, attori e prima attivita': non era il Canvas
che perdeva la conoscenza, era la conoscenza che non era mai stata sintetizzata.

Qui la sintesi diventa un passo deterministico del confine, di proprieta' del
Process Agent. Non inventa: usa l'estrattore che la review gia' usava, sul corpus
autoritativo delle fonti, e le domande non ancorate all'evidenza vengono scartate
dallo stesso filtro di sempre. Il Canvas continua a non poter scrivere il piano.

Il piano dichiara su quale set di fonti e' nato (`evidence_source_set_id`). Cosi'
"il piano e' aggiornato rispetto alle interviste?" e' una domanda con risposta:
una quarta intervista cambia il set, il piano risulta indietro e viene
risintetizzato invece di restare a descrivere un processo di tre fonti fa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from backend.agents.process_snapshot import (
    ProcessKnowledgeSnapshot,
    build_process_snapshot,
    plan_ignores_evidence,
)
from backend.process_understanding import (
    ProcessUnderstandingExtractionError,
    build_process_understanding,
)
from backend.workspace_services.write_verification import (
    PersistenceVerificationError,
    verify_review_persisted,
)

logger = logging.getLogger(__name__)

SynthesisAction = Literal[
    "reused",
    "synthesized",
    "no_evidence",
    "synthesis_failed",
    "process_not_found",
]


@dataclass(frozen=True)
class PlanSynthesis:
    """L'esito del passo che porta l'evidenza dentro il piano.

    `action` dice cosa e' successo davvero, non cosa si sperava: `reused` quando
    il piano c'era gia' ed era costruito sulle fonti di adesso, `synthesized`
    quando e' stato costruito ora, `no_evidence` quando non c'e' niente da cui
    costruirlo, `synthesis_failed` quando l'estrazione non ha prodotto un piano
    utilizzabile. Le ultime due non sono lo stesso stato e non si raccontano allo
    stesso modo: la prima e' un processo senza interviste, la seconda e' un
    guasto.
    """

    action: SynthesisAction
    snapshot: ProcessKnowledgeSnapshot | None
    reason: str = ""
    blockers: list[str] = field(default_factory=list)

    @property
    def has_plan(self) -> bool:
        return bool(self.snapshot and self.snapshot.has_semantic_model)

    def as_log_entry(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "snapshot_id": self.snapshot.snapshot_id if self.snapshot else None,
            "snapshot_label": self.snapshot.label if self.snapshot else None,
            "has_plan": self.has_plan,
        }


def plan_is_built_on(review: dict | None, source_set_id: str) -> bool:
    """Il piano salvato e' costruito sul set di fonti che c'e' adesso?

    Una review preparata prima che la colonna esistesse non dichiara nulla: e'
    `None`, che significa "non si sa", non "costruita su nessuna fonte". Un piano
    di cui non si sa la provenienza, mentre l'evidenza esiste, va risintetizzato:
    l'alternativa e' fidarsi di un piano che potrebbe ignorare un'intervista.
    """
    if not review:
        return False
    recorded = review.get("evidence_source_set_id")
    return bool(recorded) and str(recorded) == str(source_set_id)


def evidence_corpus(ledger_snapshot: dict) -> str:
    """Il materiale su cui il piano viene costruito, voce per voce.

    Le fonti con il loro testo integrale, e sotto il registro dei claim proiettati
    quando c'e'. I due piani restano separati e dichiarati: la proiezione del
    knowledge graph e' asincrona, e quando e' indietro le interviste valgono
    comunque - contarne zero perche' il grafo non ha ancora ingerito e' il modo in
    cui un processo con tre interviste diventava un processo senza evidenza.
    """
    from backend.agents.evidence_brief import render_ledger_lines, render_source_evidence
    from backend.memory import provenance

    sections = [
        "FONTI AGLI ATTI (autoritative: ogni voce resta separata dalle altre)",
        render_source_evidence(ledger_snapshot, include_content=True),
    ]

    entries = provenance.build_ledger(ledger_snapshot.get("claims") or [])
    if entries:
        sections += [
            "",
            "REGISTRO DEI CLAIM PROIETTATI (attribuzione e grado di sostegno)",
            render_ledger_lines(entries),
        ]
    elif ledger_snapshot.get("claim_status") not in {"ok", "empty"}:
        sections += [
            "",
            "La proiezione dei claim non e' disponibile in questo momento: "
            "usa il testo delle fonti, non concludere che l'evidenza sia assente.",
        ]

    return "\n".join(sections)


def synthesize_process_plan(process_id: str) -> PlanSynthesis:
    """Costruisce il piano del processo dall'evidenza agli atti e lo persiste.

    Il piano che ne esce e' preliminare per costruzione: porta con se' le lacune
    che le fonti non chiudono, e quelle diventano domande del piano invece di
    diventare un divieto di disegnarlo. Cio' che le fonti non dicono non entra:
    l'estrattore lavora sul corpus, e il filtro di ancoraggio che governa gia' le
    domande del piano scarta cio' che non cita una lacuna reale.

    Args:
        process_id: Il processo, non affidabile.

    Returns:
        L'esito, con lo snapshot aggiornato quando il piano e' stato scritto.

    Side effects:
        Scrive una nuova versione della review, e la rilegge per verificare che
        contenga davvero un piano prima di dichiarare la sintesi riuscita.
    """
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return PlanSynthesis(
            action="process_not_found",
            snapshot=None,
            reason=f"Processo non trovato: {process_id}",
        )

    ledger = load_evidence_ledger(process.get("project_id"), process_id)
    if evidence_count(ledger) == 0:
        return PlanSynthesis(
            action="no_evidence",
            snapshot=build_process_snapshot(process_id),
            reason=(
                "Il processo non ha ancora fonti ne' claim agli atti: non c'e' "
                "evidenza da cui costruire un piano."
            ),
            blockers=["Nessuna evidenza registrata per questo processo."],
        )

    corpus = evidence_corpus(ledger)
    result = build_process_understanding(process["name"], corpus)
    if result.status != "success" or result.process is None:
        failure = result.failure
        reason = failure.message if failure else "Estrazione del piano non riuscita."
        logger.warning("sintesi piano fallita per il processo %s: %s", process_id, reason)
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=reason,
            blockers=[reason],
        )

    # La regola del confine vale anche per la sintesi: un piano senza attori,
    # partecipanti ne' attivita' su un processo che ha fonti agli atti non e'
    # prudenza, e' evidenza che non e' arrivata fino al piano. Salvarlo lo
    # renderebbe lo stato ufficiale del processo, e tutto cio' che viene dopo
    # leggerebbe quel vuoto invece delle interviste.
    ignored = plan_ignores_evidence(result.process, evidence_count(ledger))
    if ignored:
        logger.warning("sintesi piano vuota per il processo %s: %s", process_id, ignored)
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=ignored,
            blockers=[ignored],
        )

    previous = workspace_database.get_bpmn_review(
        process["bpmn_model_id"], include_approved=True
    )
    previous_version = int((previous or {}).get("version") or 0)

    try:
        workspace_database.prepare_bpmn_review(
            bpmn_model_id=process["bpmn_model_id"],
            process_description=corpus,
            process_understanding=result.process.model_dump(mode="json"),
            evidence_source_set_id=str(ledger.get("source_set_id") or ""),
        )
        # Write -> persistence -> read-after-write. Un piano che il database non
        # ha non e' un piano, e dichiararlo scritto e' esattamente il difetto che
        # faceva dire "review aggiornata" davanti a una review a zero attori.
        verify_review_persisted(
            process["bpmn_model_id"],
            expect_plan_content=True,
            minimum_version=previous_version + 1,
        )
    except (ProcessUnderstandingExtractionError, PersistenceVerificationError, ValueError) as exc:
        logger.warning(
            "piano non persistito per il processo %s: %s", process_id, exc, exc_info=True
        )
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=str(exc),
            blockers=[str(exc)],
        )

    snapshot = build_process_snapshot(process_id)
    return PlanSynthesis(
        action="synthesized",
        snapshot=snapshot,
        reason=(
            f"Piano costruito su {len(ledger.get('sources') or [])} fonti "
            f"(set {ledger.get('source_set_id')})."
        ),
    )


def ensure_process_plan(process_id: str, *, force: bool = False) -> PlanSynthesis:
    """Il processo ha un piano costruito sull'evidenza che ha adesso.

    E' il passo che il confine Process -> Canvas attraversa prima di ogni run di
    modellazione. Deterministico su *quando* sintetizzare: il piano si rifa' solo
    se non c'e', o se e' nato su un set di fonti diverso da quello corrente.
    Rifarlo a ogni giro cancellerebbe le risposte che il consulente ha gia' dato,
    che sono conoscenza e non ipotesi.

    Args:
        process_id: Il processo.
        force: Risintetizza anche se il piano risulta allineato. Serve quando il
            consulente chiede esplicitamente di ricostruire dalle fonti.

    Returns:
        L'esito, con lo snapshot che il Canvas dovra' leggere.
    """
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return PlanSynthesis(
            action="process_not_found",
            snapshot=None,
            reason=f"Processo non trovato: {process_id}",
        )

    ledger = load_evidence_ledger(process.get("project_id"), process_id)
    review = workspace_database.get_bpmn_review(
        process["bpmn_model_id"], include_approved=True
    )
    snapshot = build_process_snapshot(process_id)

    if evidence_count(ledger) == 0:
        # Senza evidenza non si sintetizza, ma un piano scritto a mano resta
        # valido: e' conoscenza del consulente, non un residuo da cancellare.
        return PlanSynthesis(
            action="reused" if (snapshot and snapshot.has_semantic_model) else "no_evidence",
            snapshot=snapshot,
            reason="Nessuna evidenza agli atti per questo processo.",
            blockers=[]
            if (snapshot and snapshot.has_semantic_model)
            else ["Nessuna evidenza registrata per questo processo."],
        )

    source_set_id = str(ledger.get("source_set_id") or "")
    plan_current = (
        snapshot is not None
        and snapshot.has_semantic_model
        and plan_is_built_on(review, source_set_id)
    )
    if plan_current and not force:
        return PlanSynthesis(
            action="reused",
            snapshot=snapshot,
            reason=f"Il piano {snapshot.label} e' gia' costruito sul set di fonti corrente.",
        )

    if ledger.get("source_status") in {"error", "stale"} and snapshot and snapshot.has_semantic_model:
        # Il registro non e' stato riletto in questo turno: risintetizzare su un
        # set che potrebbe essere parziale farebbe sparire dal piano cio' che non
        # si e' riusciti a leggere. Meglio il piano di prima, dichiarato.
        return PlanSynthesis(
            action="reused",
            snapshot=snapshot,
            reason=(
                "Il set di fonti non e' leggibile in questo turno: tengo il piano "
                f"{snapshot.label} invece di ricostruirlo su un'evidenza parziale."
            ),
        )

    return synthesize_process_plan(process_id)
