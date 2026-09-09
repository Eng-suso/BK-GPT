"""Lo snapshot autoritativo del processo: cio' che il Canvas puo' sapere.

Il Process Agent possiede la conoscenza del processo; il Canvas Agent possiede
la trasformazione di quella conoscenza in BPMN. Fra i due passava, finora, il
solo `bpmn_model_id`: il Canvas riapriva il database per conto suo, leggeva il
`BPMNSemanticModel` della review e ricostruiva il resto dal testo della chat.
Da li' nascevano tre difetti distinti che sembravano uno solo:

- **la conoscenza non attraversava il confine.** La Process Chat vedeva Laura,
  Paolo e Francesca; il planner del canvas vedeva un titolo. Le fonti, i claim
  con la loro provenance, le lacune aperte e le divergenze non arrivavano mai
  dall'altra parte;
- **non esisteva una versione.** "Il canvas e' stato costruito su quale stato
  del processo?" non era una domanda a cui si potesse rispondere, quindi non
  era nemmeno una domanda a cui si potesse rispondere *male*: semplicemente non
  c'era il dato;
- **il Canvas poteva scrivere la verita'.** `prepare_canvas_bpmn_review` accetta
  prosa libera e ricostruisce da li' la ProcessUnderstanding: due passaggi e il
  disegno diventava la fonte, le interviste un ricordo.

Questo modulo tiene il confine. Non parla con l'LLM, non decide niente, non
scrive: legge lo stato persistito e ne produce **una** fotografia identificata.

L'identita' (`snapshot_id`) e' deterministica e si calcola su cio' che
costituisce conoscenza nuova: il processo, la versione della review e il set di
fonti agli atti. Non entra la proiezione dei claim, che e' asincrona e puo'
degradare: farla entrare significherebbe dichiarare "conoscenza cambiata" ogni
volta che il knowledge graph e' indietro, ed e' esattamente l'oscillazione che
il registro dell'evidenza aveva gia' dovuto togliere di mezzo. Lo stato della
proiezione viaggia comunque dentro lo snapshot (`claim_status`), dichiarato:
chi legge sa se la provenance e' completa o se e' solo in ritardo.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from backend.bpmn import BPMNSemanticModel
from backend.memory import provenance
from backend.process_understanding import ProcessUnderstanding


# Quante righe di registro e quante fonti finiscono nel blocco che il modeler
# legge. Il resto resta nello snapshot strutturato, interrogabile dai tool.
LEDGER_RENDER_LIMIT = 40


class SnapshotSource(BaseModel):
    """Una fonte agli atti, con chi ci ha parlato dentro."""

    id: str = ""
    name: str = ""
    type: str = ""
    participants: list[str] = Field(default_factory=list)
    summary: str = ""
    has_content: bool = False


class SnapshotClaim(BaseModel):
    """Un'affermazione del registro, con il sostegno che il runtime le ha contato."""

    statement: str = ""
    voice: str = ""
    source_name: str = ""
    support: str = "single_source"
    support_label: str = ""
    scope_label: str = ""
    epistemic_status: str = "reported"
    process_area: str = "other"
    quote: str = ""
    quote_verified: bool = False
    corroborating_sources: list[str] = Field(default_factory=list)
    exclusive_qualifiers: list[str] = Field(default_factory=list)


class SnapshotQuestion(BaseModel):
    """Una lacuna aperta del piano, con le alternative e cio' che e' gia' deciso."""

    question_id: str = ""
    question: str = ""
    affects: str = ""
    severity: str = "non_blocking"
    options: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    answered_at: str | None = None


class ProcessKnowledgeSnapshot(BaseModel):
    """Tutto cio' che DeliR sa di un processo, in una versione citabile.

    E' il solo oggetto che attraversa il confine Process -> Canvas. Chi lo
    riceve non deve riaprire il database per farsi un'idea propria del
    processo: se un dato non e' qui, per il Canvas quel dato non esiste, e la
    risposta giusta e' chiederlo indietro (`raise_modeling_question`), non
    dedurlo.
    """

    # --- identita' --------------------------------------------------------
    process_id: str
    project_id: str = ""
    bpmn_model_id: str = ""
    process_name: str = ""
    # La versione della review: e' il numero che il consulente vede crescere
    # quando risponde a una domanda o quando il piano viene rivisto.
    version: int = 0
    snapshot_id: str = ""
    evidence_source_set_id: str = ""

    # --- conoscenza canonica ---------------------------------------------
    process_understanding: dict[str, Any] | None = None
    bpmn_semantic_model: dict[str, Any] | None = None

    # --- evidenza ---------------------------------------------------------
    sources: list[SnapshotSource] = Field(default_factory=list)
    claims: list[SnapshotClaim] = Field(default_factory=list)
    ledger_summary: dict[str, Any] = Field(default_factory=dict)
    source_status: str = "empty"
    claim_status: str = "empty"

    # --- cio' che non si sa ancora ---------------------------------------
    open_questions: list[SnapshotQuestion] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    # --- quanto e' pronto -------------------------------------------------
    readiness_score: int | None = None
    draft_readiness: dict[str, Any] | None = None
    validation_readiness: dict[str, Any] | None = None

    @property
    def label(self) -> str:
        """Come si nomina questa versione in una frase: `V17`."""
        return f"V{self.version}"

    @property
    def has_semantic_model(self) -> bool:
        return bool(self.bpmn_semantic_model)

    @property
    def modelable(self) -> bool:
        """C'e' abbastanza per disegnare una bozza?

        La soglia e' quella della bozza, non quella dell'approvazione: un
        processo con una lacuna dichiarata resta disegnabile, ed e' proprio
        disegnandolo che la lacuna diventa visibile a chi deve chiuderla.
        """
        readiness = self.draft_readiness or {}
        return bool(
            self.has_semantic_model
            and readiness.get("status") == "modelable"
            and not (readiness.get("blockers") or [])
        )

    @property
    def blocking_questions(self) -> list[SnapshotQuestion]:
        return [
            item
            for item in self.open_questions
            if item.severity == "blocking" and not item.answer
        ]

    def as_handoff_payload(self) -> dict[str, Any]:
        """Il payload che si allega a un handoff o a un log: identita' e stato,
        senza trascinarsi dietro l'intero modello semantico."""
        return {
            "process_id": self.process_id,
            "bpmn_model_id": self.bpmn_model_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_label": self.label,
            "version": self.version,
            "evidence_source_set_id": self.evidence_source_set_id,
            "source_count": len(self.sources),
            "claim_count": len(self.claims),
            "open_question_count": len([q for q in self.open_questions if not q.answer]),
            "blocking_question_count": len(self.blocking_questions),
            "modelable": self.modelable,
            "has_semantic_model": self.has_semantic_model,
            "readiness_score": self.readiness_score,
        }


# --- costruzione ----------------------------------------------------------


def snapshot_identity(
    *,
    process_id: str,
    version: int,
    source_set_id: str,
) -> str:
    """L'identita' di uno stato di conoscenza, calcolata e non dichiarata.

    Tre ingredienti, e nessun altro: il processo, la versione del piano e il set
    di fonti agli atti. Due letture dello stesso stato danno la stessa identita';
    una risposta a una domanda aperta o una fonte in piu' ne danno una diversa,
    perche' in entrambi i casi il processo sa qualcosa che prima non sapeva.

    Args:
        process_id: Il processo.
        version: La versione della review, che il database incrementa a ogni
            preparazione, revisione o risposta.
        source_set_id: L'identita' del set di fonti, dal registro dell'evidenza.

    Returns:
        Una stringa stabile di 16 caratteri.
    """
    material = json.dumps(
        {
            "process_id": str(process_id or ""),
            "version": int(version or 0),
            "source_set_id": str(source_set_id or ""),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _snapshot_claims(entries: list[provenance.LedgerEntry]) -> list[SnapshotClaim]:
    return [
        SnapshotClaim(
            statement=entry.claim.statement,
            voice=entry.claim.voice,
            source_name=entry.claim.source_name,
            support=entry.support,
            support_label=provenance.SUPPORT_LABEL_IT.get(entry.support, entry.support),
            scope_label=entry.claim.scope_label,
            epistemic_status=entry.claim.epistemic_status,
            process_area=entry.claim.process_area,
            quote=entry.claim.quote,
            quote_verified=entry.claim.quote_verified,
            corroborating_sources=list(entry.corroborating_sources),
            exclusive_qualifiers=list(entry.exclusive_qualifiers),
        )
        for entry in entries
    ]


def build_process_snapshot(process_id: str) -> ProcessKnowledgeSnapshot | None:
    """La fotografia autoritativa di un processo, letta dallo stato persistito.

    Deterministica e in sola lettura: nessun LLM, nessuna scrittura. Chiamarla
    due volte di fila sullo stesso processo deve dare due snapshot con lo stesso
    `snapshot_id` - e' l'invariante su cui si regge "una sola verita'".

    Args:
        process_id: Il processo da fotografare, non affidabile.

    Returns:
        Lo snapshot, o ``None`` se il processo non esiste. Un processo senza
        review esiste comunque: torna uno snapshot senza modello semantico, che
        e' un'informazione diversa da "processo inesistente".
    """
    from backend import workspace_database
    from backend.graphs.common import canonical_semantic_context
    from backend.graphs.process.nodes import load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return None

    project_id = str(process.get("project_id") or "")
    bpmn_model_id = str(process.get("bpmn_model_id") or "")
    ledger_snapshot = load_evidence_ledger(project_id, process_id)
    entries = provenance.build_ledger(ledger_snapshot.get("claims") or [])
    review = (
        workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)
        if bpmn_model_id
        else None
    )

    understanding: ProcessUnderstanding | None = None
    semantic_model: BPMNSemanticModel | None = None
    if review is not None:
        understanding, semantic_model = canonical_semantic_context(
            review.get("bpmn_semantic_model")
        )

    version = int((review or {}).get("version") or 0)
    draft_readiness = None
    validation_readiness = None
    if understanding is not None:
        from backend.process_understanding import (
            draft_readiness_from_understanding,
            validation_readiness_from_understanding,
        )

        draft_readiness = draft_readiness_from_understanding(understanding)
        validation_readiness = validation_readiness_from_understanding(understanding)

    return ProcessKnowledgeSnapshot(
        process_id=process_id,
        project_id=project_id,
        bpmn_model_id=bpmn_model_id,
        process_name=str(process.get("name") or ""),
        version=version,
        snapshot_id=snapshot_identity(
            process_id=process_id,
            version=version,
            source_set_id=str(ledger_snapshot.get("source_set_id") or ""),
        ),
        evidence_source_set_id=str(ledger_snapshot.get("source_set_id") or ""),
        process_understanding=understanding.model_dump(mode="json") if understanding else None,
        bpmn_semantic_model=semantic_model.model_dump(mode="json") if semantic_model else None,
        sources=[
            SnapshotSource(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                type=str(item.get("type") or ""),
                participants=[str(voice) for voice in item.get("participants") or []],
                summary=str(item.get("summary") or ""),
                has_content=bool(item.get("has_content")),
            )
            for item in ledger_snapshot.get("sources") or []
        ],
        claims=_snapshot_claims(entries),
        ledger_summary=provenance.summarize_ledger(entries).as_dict(),
        source_status=str(ledger_snapshot.get("source_status") or "empty"),
        claim_status=str(ledger_snapshot.get("claim_status") or "empty"),
        open_questions=[
            SnapshotQuestion(**item) for item in (review or {}).get("open_questions") or []
        ],
        missing_information=list((review or {}).get("missing_information") or []),
        readiness_score=(review or {}).get("readiness_score"),
        draft_readiness=draft_readiness,
        validation_readiness=validation_readiness,
    )


def snapshot_is_current(process_id: str, snapshot_id: str) -> bool:
    """Lo snapshot su cui si sta lavorando e' ancora quello vero?

    Serve al Canvas alla fine di un run: se nel frattempo il Process Agent ha
    registrato una risposta o una fonte, il disegno appena prodotto descrive uno
    stato che non e' piu' quello ufficiale. Non e' un errore - e' il momento in
    cui il Canvas deve rileggere e ridisegnare sulla versione nuova.
    """
    if not snapshot_id:
        return False
    current = build_process_snapshot(process_id)
    return current is not None and current.snapshot_id == snapshot_id


# --- il piano rifiuta di ignorare l'evidenza ------------------------------


def plan_ignores_evidence(
    understanding: ProcessUnderstanding | dict | None,
    recorded_evidence: int,
) -> str | None:
    """Il piano riparte da zero mentre l'evidenza esiste: perche', se e' cosi'.

    PROCESS-V2-11: dopo tre interviste il planner dichiarava di conoscere
    "esclusivamente il titolo del processo" e preparava una review con zero
    attori e zero lane. Non e' prudenza, e' evidenza che non e' arrivata fin
    qui: salvarla come piano la renderebbe lo stato ufficiale del processo, e
    tutto cio' che viene dopo leggerebbe quel vuoto invece delle interviste.

    Il controllo vive qui e non nel tool di modeling perche' non e' una regola
    del modeling: e' la regola del confine. Il Canvas ha una sua strada per
    scrivere la review (`prepare_canvas_bpmn_review`, che ricostruisce la
    ProcessUnderstanding da prosa libera), e senza questo controllo quella
    strada e' una seconda source of truth con l'aspetto di un tool innocuo.

    Args:
        understanding: Il ProcessUnderstanding che la review vorrebbe salvare.
        recorded_evidence: Quanta evidenza il processo ha agli atti, fonti o
            claim che siano - la proiezione dei claim arriva dopo, e nel
            frattempo le fonti valgono comunque.

    Returns:
        Il motivo del rifiuto, o ``None`` se il piano regge.
    """
    if recorded_evidence == 0:
        return None
    if understanding is None:
        return (
            f"Il processo ha {recorded_evidence} evidenze registrate ma la review "
            "arriva senza ProcessUnderstanding strutturata."
        )

    model = (
        understanding
        if isinstance(understanding, ProcessUnderstanding)
        else ProcessUnderstanding.model_validate(understanding)
    )
    if model.actors or model.participants or model.steps:
        return None
    return (
        f"Il processo ha {recorded_evidence} evidenze registrate, ma la "
        "ProcessUnderstanding proposta non contiene attori, partecipanti ne' "
        "attivita'."
    )


PLAN_IGNORES_EVIDENCE_REMEDY = (
    "Rileggi il registro dell'evidenza di questo processo (e' nel tuo contesto "
    "di scope, e audit_process_evidence lo riporta riga per riga), struttura "
    "attori, partecipanti e attivita' su quello che le fonti hanno gia' detto, "
    "poi ripresenta la review. Se il registro davvero non basta per una bozza, "
    "dillo al consulente citando cosa manca invece di salvare un piano vuoto."
)


def assert_plan_respects_evidence(
    process_id: str,
    understanding: ProcessUnderstanding | dict | None,
) -> None:
    """Alza `ValueError` se la review sta per cancellare l'evidenza agli atti."""
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    snapshot = load_evidence_ledger(process.get("project_id"), process_id)
    reason = plan_ignores_evidence(understanding, evidence_count(snapshot))
    if reason:
        raise ValueError(f"{reason} {PLAN_IGNORES_EVIDENCE_REMEDY}")


# --- resa leggibile per chi modella ---------------------------------------


def render_snapshot_for_modeling(snapshot: ProcessKnowledgeSnapshot) -> str:
    """Lo snapshot come lo legge un process modeler.

    Non e' una sintesi: e' l'elenco di cio' che il processo sa, di chi lo dice e
    di quanto e' sostenuto, piu' l'elenco di cio' che non sa. Il modeler deve
    poter distinguere "corroborato da due voci" da "lo dice solo Paolo" prima di
    decidere se una cosa diventa il percorso principale o un'eccezione.
    """
    lines = [
        f"Snapshot conoscenza processo {snapshot.label} (id: {snapshot.snapshot_id}).",
        f"Processo: {snapshot.process_name or snapshot.process_id}.",
        f"Fonti agli atti: {len(snapshot.sources)} (set: {snapshot.evidence_source_set_id or 'non disponibile'}).",
    ]

    if snapshot.source_status in {"error", "stale"}:
        lines.append(
            "Attenzione: il set di fonti non e' stato riletto in questo turno; "
            "non concludere che le fonti siano zero."
        )
    if snapshot.claim_status not in {"ok", "empty"}:
        lines.append(
            "Attenzione: la proiezione dei claim e' incompleta; la provenance "
            "qui sotto puo' essere parziale, le fonti no."
        )

    if snapshot.sources:
        lines.append("")
        lines.append("Fonti:")
        for source in snapshot.sources:
            voices = ", ".join(source.participants) or "partecipanti non dichiarati"
            lines.append(f"- {source.name} [{source.type or 'fonte'}] — {voices}")

    if snapshot.claims:
        lines.append("")
        lines.append("Registro dell'evidenza (affermazione | voce | sostegno):")
        for claim in snapshot.claims[:LEDGER_RENDER_LIMIT]:
            scope = f" | ambito: {claim.scope_label}" if claim.scope_label.strip() else ""
            only = (
                f" | solo {claim.voice}: " + ", ".join(claim.exclusive_qualifiers)
                if claim.exclusive_qualifiers
                else ""
            )
            also = (
                " | anche: " + ", ".join(claim.corroborating_sources)
                if claim.corroborating_sources
                else ""
            )
            lines.append(
                f"- {claim.statement} | voce: {claim.voice or 'non dichiarata'} "
                f"| sostegno: {claim.support_label or claim.support}{scope}{also}{only}"
            )
        if len(snapshot.claims) > LEDGER_RENDER_LIMIT:
            lines.append(
                f"- (+{len(snapshot.claims) - LEDGER_RENDER_LIMIT} altre affermazioni "
                "nello snapshot strutturato)"
            )

    open_questions = [item for item in snapshot.open_questions if not item.answer]
    if open_questions:
        lines.append("")
        lines.append("Lacune aperte (non inventare la risposta: modella l'incertezza o richiedila):")
        for question in open_questions:
            options = (
                " | alternative: " + "; ".join(
                    str(option.get("label") or "") for option in question.options
                )
                if question.options
                else ""
            )
            lines.append(
                f"- [{question.severity}] {question.question} "
                f"(tocca: {question.affects or 'non dichiarato'}){options}"
            )

    answered = [item for item in snapshot.open_questions if item.answer]
    if answered:
        lines.append("")
        lines.append("Decisioni gia' prese dal consulente (sono conoscenza, usale):")
        for question in answered:
            lines.append(f"- {question.question} -> {question.answer}")

    if snapshot.missing_information:
        lines.append("")
        lines.append("Da sistemare nel piano:")
        lines.extend(f"- {item}" for item in snapshot.missing_information[:12])

    lines.append("")
    lines.append(
        f"Bozza disegnabile: {'si' if snapshot.modelable else 'no'} | "
        f"readiness: {snapshot.readiness_score if snapshot.readiness_score is not None else 'non calcolata'} | "
        f"modello semantico: {'presente' if snapshot.has_semantic_model else 'assente'}."
    )
    return "\n".join(lines)
