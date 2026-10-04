from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field


def _iso_date(value: str | None) -> str | None:
    """Valida una data del workspace al confine, dove il payload smette di essere testo.

    Args:
        value: Data non affidabile in arrivo dal client. ``None`` significa "non
            l'ho detto", stringa vuota "toglila", una data ISO la registra.

    Returns:
        La data normalizzata in ``YYYY-MM-DD``, la stringa vuota, o ``None``.

    Raises:
        ValueError: Se la stringa non e' una data ISO. Una data illeggibile va
            rifiutata qui: piu' a valle diventerebbe una colonna con dentro
            "prossimo mese".
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("Data non valida: usa il formato YYYY-MM-DD.") from exc


# `None` lascia il campo com'e', `""` lo svuota, una data ISO lo registra: le
# stesse tre intenzioni che gli altri campi testuali esprimono gia'.
IsoDate = Annotated[str | None, AfterValidator(_iso_date)]


class CreateClientRequest(BaseModel):
    # Ogni campo oltre al nome e' opzionale davvero: `None` significa "non
    # dichiarato" e il placeholder lo mette `workspace_database.create_client`,
    # in un punto solo. Vedi `backend/workspace_defaults.py`.
    name: str
    sector: str | None = None
    status: str | None = None
    owner: str | None = None
    contact: str | None = None


class UpdateClientRequest(BaseModel):
    # Patch parziale: `None` significa "non toccare questo campo". Il consulente
    # modifica un campo alla volta dalla UI e non deve rimandare tutto il record.
    name: str | None = None
    sector: str | None = None
    status: str | None = None
    owner: str | None = None
    contact: str | None = None


class MilestoneModel(BaseModel):
    # Il traguardo e se e' stato raggiunto. `completed_at` lo scrive il backend
    # quando lo stato passa a `done`: una data su una milestone non raggiunta
    # sarebbe la traccia di uno stato che non esiste.
    title: str
    status: str = "planned"
    completed_at: str | None = None


class CreateProjectRequest(BaseModel):
    # Come per il cliente: `None` e' "non dichiarato", e il placeholder lo mette
    # `workspace_database.create_project`. Vedi `backend/workspace_defaults.py`.
    client_id: str
    name: str
    objective: str | None = None
    lead: str | None = None
    start_date: IsoDate = None
    end_date: IsoDate = None
    phase: str | None = None
    status: str | None = None
    progress: int = 0
    next_step: str | None = None
    milestones: list[MilestoneModel | str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class UpdateProjectRequest(BaseModel):
    # Patch parziale. Le liste arrivano intere quando arrivano: `[]` svuota,
    # `None` lascia com'e'.
    name: str | None = None
    client_id: str | None = None
    objective: str | None = None
    lead: str | None = None
    start_date: IsoDate = None
    end_date: IsoDate = None
    phase: str | None = None
    status: str | None = None
    progress: int | None = None
    next_step: str | None = None
    # Una voce inviata come solo titolo conserva lo stato che aveva: la lista
    # dice *cosa* promette il progetto, non annulla cio' che e' gia' successo.
    milestones: list[MilestoneModel | str] | None = None
    open_issues: list[str] | None = None
    deliverables: list[str] | None = None


class CreateProcessRequest(BaseModel):
    # `None` = "non dichiarato": il placeholder lo mette
    # `workspace_database.create_process`, in un punto solo.
    name: str
    stage: str | None = None
    status: str | None = None
    owner: str | None = None
    readiness: int = 0


class UpdateProcessRequest(BaseModel):
    # Patch parziale: un campo non dichiarato resta com'e'.
    name: str | None = None
    stage: str | None = None
    status: str | None = None
    owner: str | None = None
    readiness: int | None = None


class CreateProjectSourceRequest(BaseModel):
    name: str
    type: str = "Fonte"
    meta: str = ""
    process_id: str | None = None


class CreateProjectDecisionRequest(BaseModel):
    title: str
    owner: str = "Da assegnare"
    status: str = "Aperta"
    process_id: str | None = None


class UpdateBpmnModelRequest(BaseModel):
    xml: str
    # La versione da cui il canvas e' partito. Se nel frattempo ne e' nata
    # un'altra, il salvataggio risponde 409 invece di sovrascriverla.
    expected_version_id: int | None = None


class UpdateBpmnReviewRequest(BaseModel):
    bpmn_brief: str


class ArchiveRequest(BaseModel):
    # Perche' e' stato chiuso. Facoltativo, ma e' l'unica cosa che distingue
    # "finito bene" da "non se n'e' fatto niente" quando lo si rilegge fra un anno.
    reason: str | None = None


class ArchiveImpactResponse(BaseModel):
    """Cosa si porta dietro chiudere o eliminare un record."""

    id: str
    name: str
    projects: int
    processes: int
    sources: int
    decisions: int


class ClientResponse(BaseModel):
    id: str
    name: str
    sector: str
    status: str
    projects: int
    next_activity: str
    owner: str
    contact: str
    processes: list[str]
    documents: list[str]
    archived_at: str | None = None
    archive_reason: str | None = None


class ProjectProcessResponse(BaseModel):
    id: str
    project_id: str
    bpmn_model_id: str
    name: str
    stage: str
    status: str
    owner: str
    readiness: int
    archived_at: str | None = None
    archive_reason: str | None = None


class BpmnModelResponse(BaseModel):
    id: str
    process_id: str
    name: str
    xml: str | None = None
    # L'ultima versione salvata: il canvas la rimanda al salvataggio successivo.
    version_id: int | None = None


class BpmnVersionResponse(BaseModel):
    id: int
    bpmn_model_id: str
    process_id: str
    xml: str
    change_summary: str
    source: str
    created_at: str


class RestoreBpmnVersionResponse(BaseModel):
    bpmn_model: BpmnModelResponse
    restored_from: BpmnVersionResponse
    created_version: BpmnVersionResponse


class BpmnReviewResponse(BaseModel):
    bpmn_model_id: str
    process_id: str
    version: int = 1
    source_text: str
    process_understanding: dict[str, Any] = Field(default_factory=dict)
    bpmn_semantic_model: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    bpmn_brief: str
    readiness_score: int
    missing_information: list[str]
    open_questions: list[ReviewOpenQuestionResponse] = Field(default_factory=list)
    answers: list[ReviewAnswerResponse] = Field(default_factory=list)
    status: str = "pending"
    created_at: str
    updated_at: str


class ReviewOptionResponse(BaseModel):
    """One alternative the agent proposed for an open question."""

    label: str
    implication: str = ""


class ReviewOpenQuestionResponse(BaseModel):
    """A gap in the plan the consultant can actually close."""

    question_id: str
    question: str
    affects: str = ""
    severity: str = "non_blocking"
    options: list[ReviewOptionResponse] = Field(default_factory=list)
    answer: str | None = None
    answered_at: str | None = None


class ReviewAnswerResponse(BaseModel):
    question_id: str
    question: str
    answer: str
    answered_at: str


class AnswerBpmnReviewQuestionRequest(BaseModel):
    """The consultant's answer: a proposed option, or their own words."""

    question: str
    answer: str


class BpmnReviewVersionResponse(BaseModel):
    """One recorded state of a review, with why it was written."""

    bpmn_model_id: str
    process_id: str
    version: int
    status: str
    change_summary: str
    source: str
    source_text: str
    process_understanding: dict[str, Any] = Field(default_factory=dict)
    bpmn_semantic_model: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    bpmn_brief: str
    readiness_score: int
    missing_information: list[str]
    open_questions: list[ReviewOpenQuestionResponse] = Field(default_factory=list)
    answers: list[ReviewAnswerResponse] = Field(default_factory=list)
    created_at: str


class ReviseBpmnReviewRequest(BaseModel):
    """A corrected ProcessUnderstanding: the plan is rebuilt from it."""

    process_understanding: dict[str, Any]
    change_summary: str = ""


class ApproveBpmnReviewResponse(BaseModel):
    bpmn_model: BpmnModelResponse
    review: BpmnReviewResponse


class ProvenanceElementResponse(BaseModel):
    kind: Literal["actor", "participant", "step", "decision", "exception", "event", "flow"]
    element_id: str
    label: str
    status: Literal["verified", "paraphrased", "label_grounded", "unverified"]
    source_ref: str
    source_id: str = ""
    source_name: str = ""
    quote: str = ""
    consultant_decision: Literal["confirmed", "rejected"] | None = None
    # L'esito che il disegno mostra sul nodo: quello della verifica, o
    # `confirmed` quando un'inferenza e' stata confermata dal consulente.
    mark_status: Literal["verified", "paraphrased", "label_grounded", "unverified", "confirmed"]
    # Il rifiuto toglie l'elemento dal piano: vale per passaggi, eventi ed
    # eccezioni, non per attori e decisioni.
    removable: bool = False


class ProcessProvenanceResponse(BaseModel):
    """Il piano confrontato con le fonti.

    `has_plan=False` con `total=0` significa "non c'e' un piano da verificare",
    che e' diverso da "un piano con zero elementi verificati": chi legge deve
    poterli distinguere senza dedurlo dai numeri.
    """

    process_id: str
    snapshot_id: str
    snapshot_label: str
    has_plan: bool
    total: int = 0
    verified: int = 0
    paraphrased: int = 0
    label_grounded: int = 0
    unverified: int = 0
    awaiting_confirmation: int = 0
    grounded_ratio: float = 0.0
    sources_checked: int = 0
    unused_sources: list[str] = Field(default_factory=list)
    elements: list[ProvenanceElementResponse] = Field(default_factory=list)


class ElementReviewRequest(BaseModel):
    source_ref: str = Field(min_length=1)
    decision: Literal["confirmed", "rejected"]
    note: str = ""


class ElementReviewResponse(BaseModel):
    """L'esito di una revisione, con il rapporto riletto dopo la scrittura.

    `ok=False` non e' un errore di trasporto: la decisione puo' essere stata
    registrata e il disegno non aggiornato, e chi legge deve sapere quale delle
    due cose e' successa (`reason_code`).
    """

    ok: bool
    reason_code: str
    reason: str
    provenance: ProcessProvenanceResponse | None = None
    draft_status: str | None = None
    pending_verification: list[str] = Field(default_factory=list)


class BpmnDraftResponse(BaseModel):
    """L'esito del comando «genera la bozza BPMN dal piano».

    `pending_verification` non e' un errore: sono le lacune che il piano dichiara
    ancora aperte, consegnate accanto al disegno invece che al posto del disegno.
    `metrics` porta le durate di fase, cosi' «dove se ne vanno i secondi» ha una
    risposta con dei numeri.
    """

    status: Literal["drafted", "failed", "refused_by_mode"]
    reason_code: str
    process_id: str
    bpmn_model_id: str
    snapshot_id: str = ""
    snapshot_label: str = ""
    bpmn_model: BpmnModelResponse | None = None
    pending_verification: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    reason: str = ""
    # Durate in millisecondi e conteggi; `process_snapshot_version` puo' essere
    # nullo quando il processo non ha ancora una versione di piano.
    metrics: dict[str, int | None] = Field(default_factory=dict)
    # La verifica disegno-piano-fonti fatta sul canvas salvato: verdetto
    # (`conformant` | `not_conformant` | `incomplete`), rilievi con le citazioni
    # verificate, e lo snapshot su cui e' stata fatta.
    conformance: dict[str, Any] | None = None


class ConformanceStatusResponse(BaseModel):
    """L'ultima verifica di conformita' di un processo, e se descrive ancora cio' che si vede."""

    process_id: str
    snapshot_id: str = ""
    snapshot_label: str = ""
    # Un confronto e' in coda o sta girando: cio' che si legge sotto descrive il
    # disegno di prima.
    running: bool = False
    is_current: bool = False
    report: dict[str, Any] | None = None


SourceRole = Literal["context", "process_evidence", "policy", "operational_data"]


class ProjectSourceResponse(BaseModel):
    id: str
    # Vuoto per una fonte del cliente (P1.16), che vale per tutti i suoi progetti.
    project_id: str | None = None
    client_id: str | None = None
    process_id: str | None = None
    name: str
    type: str
    meta: str
    roles: list[Literal["context", "process_evidence", "policy", "operational_data"]] = Field(
        default_factory=list
    )
    retention: Literal["persistent", "temporary"] = "persistent"
    scopes: list[dict[str, str]] = Field(default_factory=list)
    status: str = "reference"
    content_hash: str | None = None
    byte_size: int | None = None
    mime_type: str | None = None
    # La lettura del file caricato: `pending` (in coda o in lettura), `done`,
    # `partial` (una parte non acquisita, il motivo e' in `meta`), `failed`.
    # `None` per le fonti senza file.
    acquisition_status: Literal["pending", "done", "partial", "failed"] | None = None
    acquisition_error: str | None = None
    # L'estrazione delle affermazioni (P1.12): `None` finche' nessuno l'ha chiesta.
    claims_status: Literal["pending", "done", "failed"] | None = None
    claims_error: str | None = None
    # Il confronto con gli altri file del processo (P1.13).
    reconcile_status: Literal["pending", "done", "failed"] | None = None


class UploadedSourceResponse(ProjectSourceResponse):
    """La fonte appena caricata, e se il caricamento l'ha creata adesso.

    `created == False` vuol dire che lo stesso file c'era gia' tra le Fonti: la
    card del composer, tolta prima dell'invio, non deve scartarlo.
    """

    created: bool = True
    # A cosa sembra servire il file, dal nome e dal formato: una proposta che
    # la card mostra se e' diversa dai ruoli che la fonte ha. `None` = il nome
    # non dice niente.
    suggested_roles: list[SourceRole] | None = None


class UpdateSourceRolesRequest(BaseModel):
    """A cosa serve una fonte: un attributo che si cambia, non la sua identita'."""

    roles: list[SourceRole] = Field(min_length=1, max_length=4)



class SourceClaimResponse(BaseModel):
    """Un'affermazione di una fonte, con la porzione che la sostiene."""

    id: int
    source_id: str
    statement: str
    segment_ordinal: int
    anchor_ref: str
    quote: str
    # La citazione e' stata ritrovata parola per parola nella porzione.
    quote_verified: bool
    extracted_at: str


class ClaimRelationSide(BaseModel):
    """Un lato di una relazione: l'affermazione, il suo file e la sua porzione."""

    claim_id: int
    source_id: str
    source_name: str
    statement: str
    anchor_ref: str
    quote: str
    quote_verified: bool


DivergenceType = Literal[
    "incompatible",
    "scope_difference",
    "formalization_difference",
    "knowledge_gap",
    "complementary",
    "tension_to_explore",
]


class ClaimRelationResponse(BaseModel):
    """Due affermazioni di file diversi sullo stesso fatto (P1.13).

    `claim` e' l'affermazione della fonte richiesta, `other` quella dell'altro
    file. `divergence_type` e' quello che le regole lasciano: puo' solo essere
    piu' debole di `declared_type`, e `reasons` dice perche'.
    """

    id: int
    kind: Literal["corroboration", "divergence"]
    divergence_type: DivergenceType | None = None
    divergence_label: str | None = None
    declared_type: DivergenceType | None = None
    reasons: list[str] = Field(default_factory=list)
    explanation: str = ""
    claim: ClaimRelationSide
    other: ClaimRelationSide


class EvidenceSegmentResponse(BaseModel):
    """Una porzione citabile di una fonte: `Ordini!B7`, `#/texts/12`."""

    id: int
    source_id: str
    # La posizione nella fonte: e' il numero che un'affermazione cita.
    ordinal: int = 0
    kind: str
    ref: str
    locator: dict[str, Any]
    text: str
    value_type: str
    value: Any = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SourceDocumentResponse(BaseModel):
    """La fonte com'e' davvero, non la riga che la riassume.

    Il pannello Fonti mostrava solo `meta`: una nota di due righe. Chi apre una
    fonte vuole leggere l'intervista, non il suo sommario - e per verificare un
    claim serve il testo, non l'etichetta. Qui la fonte porta la sua sintesi e
    il suo testo integrale.
    """

    id: str
    # Vuoto per una fonte del cliente (P1.16).
    project_id: str | None = None
    process_id: str | None = None
    name: str
    type: str
    summary: str = ""
    participants: list[str] = Field(default_factory=list)
    occurred_at: str | None = None
    episode_id: str | None = None
    content: str = ""
    has_content: bool = False


class ProjectDecisionResponse(BaseModel):
    id: str
    project_id: str
    process_id: str | None = None
    title: str
    owner: str
    status: str


class ProjectResponse(BaseModel):
    id: str
    client_id: str
    client: str
    name: str
    objective: str = ""
    lead: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    phase: str
    status: str
    progress: int
    processes: int
    next_step: str
    milestones: list[MilestoneModel]
    open_issues: list[str]
    deliverables: list[str]
    archived_at: str | None = None
    archive_reason: str | None = None
    process_items: list[ProjectProcessResponse] = Field(default_factory=list)


class WorkspaceNotification(BaseModel):
    """Un avviso: cosa e' successo, a quale processo, e se e' gia' stato letto.

    Il testo non arriva da qui: il backend dice il fatto, la lingua la sceglie
    l'interfaccia.
    """

    id: str
    kind: Literal[
        "plan_ready",
        "plan_failed",
        "conformance_findings",
        "simulation_done",
        "simulation_failed",
    ]
    occurred_at: str
    read: bool = False
    process_id: str
    process_name: str
    project_id: str
    project_name: str
    client_name: str
    bpmn_model_id: str | None = None
    #: Quanti rilievi ha trovato il confronto con le fonti.
    count: int = 0
    #: La versione del piano appena ricostruito.
    version: int | None = None
    #: Il perche' di un guasto, o il nome dello scenario simulato.
    detail: str = ""
    run_id: int | None = None


class WorkspaceNotificationsResponse(BaseModel):
    items: list[WorkspaceNotification] = Field(default_factory=list)
    #: Quanti degli avvisi restituiti nessuno ha ancora letto.
    unread: int = 0


class MarkNotificationsReadRequest(BaseModel):
    #: Gli avvisi da segnare come letti; vuoto significa "tutti quelli mostrati".
    ids: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=200
    )


class WorkspaceSearchHit(BaseModel):
    """Una cosa trovata nel workspace, con dove vive e cosa serve per aprirla."""

    kind: Literal["client", "project", "process", "source"]
    id: str
    title: str
    #: Dove si trova, gia' scritto per chi legge: "Esaote · Acquisti · As-is".
    context: str = ""
    client_id: str | None = None
    client_name: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    process_id: str | None = None
    #: Solo per le fonti: intervista, documento, nota.
    source_type: str | None = None


class ModelLibraryItem(BaseModel):
    """Un modello BPMN nella libreria, con cio' che serve per decidere se riaprirlo."""

    bpmn_model_id: str
    name: str
    #: Se il disegno esiste: un processo appena creato ha il modello ma non l'XML.
    has_diagram: bool
    #: Quante versioni del disegno sono state salvate.
    version_count: int = 0
    last_saved_at: str | None = None
    process_id: str
    process_name: str
    process_stage: str
    project_id: str
    project_name: str
    client_id: str
    client_name: str
    #: `pending` / `approved`; `None` quando il piano non e' mai stato preparato.
    review_status: str | None = None
    review_version: int | None = None
    readiness_score: int | None = None
    review_updated_at: str | None = None
    #: Ultimo verdetto del confronto con le fonti; `None` se mai confrontato.
    conformance_verdict: str | None = None
    conformance_findings: int = 0
    #: Il disegno o il piano sono cambiati e il confronto deve ancora girare.
    conformance_pending: bool = False


class ArchiveResponse(BaseModel):
    """La sezione Archivio: cio' che e' stato chiuso, non cio' che e' sparito."""

    clients: list[ClientResponse] = Field(default_factory=list)
    projects: list[ProjectResponse] = Field(default_factory=list)
    processes: list[ProjectProcessResponse] = Field(default_factory=list)
