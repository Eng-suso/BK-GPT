from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from backend.local_store import local_engine

DATA_DIR = Path("data")


class WorkspaceBase(DeclarativeBase):
    pass


class WorkspaceClient(WorkspaceBase):
    __tablename__ = "workspace_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    contact: Mapped[str] = mapped_column(String, nullable=False)
    # Un incarico che finisce non sparisce: esce dal lavoro corrente e resta
    # consultabile in archivio. `archived_at` vuoto = attivo.
    archived_at: Mapped[str | None] = mapped_column(String, index=True)
    archive_reason: Mapped[str | None] = mapped_column(Text)

    projects: Mapped[list["WorkspaceProject"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )


class WorkspaceProject(WorkspaceBase):
    __tablename__ = "workspace_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("workspace_clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Perche' il progetto esiste, e cosa lo chiude. Senza questo campo il record
    # conservava il contenitore (fase, stato, avanzamento) ma perdeva l'incarico:
    # la Project Chat sapeva come si chiamava il progetto e non cosa doveva farci
    # (bug PROJECT-01).
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Chi segue l'incarico e fra quali date sta. Il referente mostrato
    # nell'elenco era preso in prestito dal primo processo registrato, quindi
    # mancava sui progetti senza processi e ne mostrava uno a caso su quelli con
    # tre. Date in ISO `YYYY-MM-DD`: validate al confine Pydantic, non qui.
    lead: Mapped[str | None] = mapped_column(String)
    start_date: Mapped[str | None] = mapped_column(String)
    end_date: Mapped[str | None] = mapped_column(String)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    process_count: Mapped[int] = mapped_column(Integer, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    milestones_json: Mapped[str] = mapped_column(Text, nullable=False)
    open_issues_json: Mapped[str] = mapped_column(Text, nullable=False)
    deliverables_json: Mapped[str] = mapped_column(Text, nullable=False)
    archived_at: Mapped[str | None] = mapped_column(String, index=True)
    archive_reason: Mapped[str | None] = mapped_column(Text)

    client: Mapped[WorkspaceClient] = relationship(back_populates="projects")
    processes: Mapped[list["WorkspaceProcess"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="WorkspaceProcess.name",
    )


class WorkspaceProcess(WorkspaceBase):
    __tablename__ = "workspace_processes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id"), nullable=False, index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    readiness: Mapped[int] = mapped_column(Integer, nullable=False)
    archived_at: Mapped[str | None] = mapped_column(String, index=True)
    archive_reason: Mapped[str | None] = mapped_column(Text)

    project: Mapped[WorkspaceProject] = relationship(back_populates="processes")
    review_actions: Mapped[list["WorkspaceImpactReviewAction"]] = relationship(
        cascade="all, delete-orphan",
    )
    bpmn_model: Mapped["WorkspaceBpmnModel"] = relationship(
        back_populates="process",
        cascade="all, delete-orphan",
        uselist=False,
    )


class WorkspaceImpactReviewAction(WorkspaceBase):
    """Consultant hypotheses and follow-ups, separate from the As-Is authority."""

    __tablename__ = "workspace_impact_review_actions"
    __table_args__ = (
        CheckConstraint("kind IN ('candidate', 'as_is_proposal', 'clarification', 'deferred')", name="ck_impact_review_kind"),
        Index("ix_impact_review_process_tenant", "process_id", "tenant_id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    process_id: Mapped[str] = mapped_column(ForeignKey("workspace_processes.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    node_name: Mapped[str] = mapped_column(String, nullable=False)
    base_revision: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_xml: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceBpmnModel(WorkspaceBase):
    __tablename__ = "workspace_bpmn_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    process_id: Mapped[str] = mapped_column(ForeignKey("workspace_processes.id"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    xml: Mapped[str | None] = mapped_column(Text)

    process: Mapped[WorkspaceProcess] = relationship(back_populates="bpmn_model")


class WorkspaceBpmnVersion(WorkspaceBase):
    __tablename__ = "workspace_bpmn_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceBpmnReview(WorkspaceBase):
    """The current review for one BPMN model - the head of its version history.

    Same shape as WorkspaceBpmnModel / WorkspaceBpmnVersion: this row is what the
    canvas and the agent read, and every state it has ever been in is kept in
    WorkspaceBpmnReviewVersion. A review used to be a single slot that each new
    `prepare` overwrote, so a plan could not be iterated and nothing could be
    compared against what it replaced.
    """

    __tablename__ = "workspace_bpmn_reviews"

    bpmn_model_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    process_understanding_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_semantic_model_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_brief: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_information_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Su quale set di fonti questo piano e' stato costruito. NULL significa "non
    # si sa", che non e' "nessuna fonte": il runtime lo tratta come un piano da
    # risintetizzare quando l'evidenza esiste.
    evidence_source_set_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Risposte del consulente alle domande aperte del piano: cio' che l'umano ha
    # deciso, tenuto separato da cio' che il modello ha estratto.
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Le decisioni del consulente sugli elementi che nessuna fonte regge, per
    # riferimento di tracciabilita' (`steps:apri_richiesta`): confermato da chi
    # conosce il processo, o rifiutato e tolto dal piano. E' conoscenza umana, e
    # come le risposte resta separata da cio' che il modello ha estratto.
    element_decisions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # L'ultima verifica di conformita' fra canvas, piano e fonti: verdetto,
    # rilievi e lo snapshot su cui e' stata fatta. NULL: mai verificato.
    conformance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # `pending` quando il disegno o il piano sono cambiati e il confronto deve
    # ancora girare, `done` quando il rapporto qui accanto descrive cio' che c'e'.
    # E' una colonna e non un campo del JSON perche' il worker la interroga.
    conformance_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Quando la riga e' stata presa in carico. Una presa in carico senza scadenza
    # e' il modo in cui una coda si blocca in silenzio: se chi lavorava muore, la
    # riga deve tornare eleggibile da sola.
    conformance_leased_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # Quante volte la riga e' stata presa in carico per lo stesso disegno. Oltre
    # il tetto la coda smette (`failed`); un disegno nuovo la riporta a zero.
    conformance_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceBpmnReviewVersion(WorkspaceBase):
    """One recorded state of a review: what it said, and why it was written."""

    __tablename__ = "workspace_bpmn_review_versions"
    __table_args__ = (
        UniqueConstraint("bpmn_model_id", "version", name="uq_bpmn_review_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    process_understanding_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_semantic_model_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bpmn_brief: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_information_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source_set_id: Mapped[str | None] = mapped_column(String, nullable=True)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # Why this version exists: prepared from a description, revised by the
    # consultant, approved. Reader-facing, so the history is legible.
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String, nullable=False, default="prepare")
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceSimulationRun(WorkspaceBase):
    __tablename__ = "workspace_simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    bpmn_model_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scenario_name: Mapped[str] = mapped_column(String, nullable=False)
    engine: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, index=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String)


class WorkspaceSimulationRunArtifact(WorkspaceBase):
    """Heavy replay payload for a simulation run, kept out of the run row so
    listing / fetching runs stays cheap. One row per run."""

    __tablename__ = "workspace_simulation_run_artifacts"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_simulation_runs.id"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    replay_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Full-log KPIs / percentiles / bottleneck — the metric source of truth.
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Display representation: sampled case paths + bucketed series + flow volumes.
    replay_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceEventLog(WorkspaceBase):
    """Un event log reale caricato su un processo (SIM-15).

    Il file resta com'era (`WorkspaceEventLogPayload`); qui si tiene cio' che
    serve all'anteprima (formato, separatore, colonne, righe) e l'esito
    dell'ultimo mapping applicato: il mapping stesso, il template da cui viene,
    il report di qualita', i KPI e l'abbinamento delle attivita' al BPMN.
    L'event log canonico non si salva: si ricostruisce dal file e dal mapping,
    che sono deterministici.

    `status`: `uploaded` finche' nessun mapping e' stato applicato, poi `mapped`.
    Lo stesso file ricaricato sullo stesso processo ritrova la sua riga.
    """

    __tablename__ = "workspace_event_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "process_id", "content_hash", name="uq_workspace_event_log_file"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    # Il separatore in uso: quello riconosciuto, o quello indicato dal consulente.
    delimiter: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    columns_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    mapping_json: Mapped[str | None] = mapped_column(Text)
    # La versione esatta del template applicato; NULL = mapping scritto a mano.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_event_log_templates.id", ondelete="SET NULL")
    )
    # Le attivita' abbinate dal consulente; NULL = solo il suggerimento automatico.
    activity_matches_json: Mapped[str | None] = mapped_column(Text)
    # Le risorse del log abbinate dal consulente alle risorse del modello.
    resource_matches_json: Mapped[str | None] = mapped_column(Text)
    # La versione del BPMN su cui e' stato calcolato l'abbinamento.
    bpmn_version_id: Mapped[int | None] = mapped_column(Integer)
    quality_json: Mapped[str | None] = mapped_column(Text)
    summary_json: Mapped[str | None] = mapped_column(Text)
    match_json: Mapped[str | None] = mapped_column(Text)
    resource_match_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    mapped_at: Mapped[str | None] = mapped_column(String)


class WorkspaceEventLogPayload(WorkspaceBase):
    """I byte del file caricato, fuori dalla riga del log come il replay dei run:
    elencare i log non deve leggere megabyte."""

    __tablename__ = "workspace_event_log_payloads"

    event_log_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_event_logs.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class WorkspaceEventLogTemplate(WorkspaceBase):
    """Un mapping salvato, versionato: lo stesso export di un sistema si rimappa
    con un clic.

    Una riga per versione. `template_key` tiene insieme le versioni dello stesso
    template; salvarlo di nuovo aggiunge una versione, non riscrive la vecchia,
    cosi' un log mappato con la versione 2 dice ancora con quale mapping.
    Vive nel tenant, non nel progetto: l'export di SAP e' lo stesso per tutti i
    progetti dello stesso cliente e di clienti diversi.
    """

    __tablename__ = "workspace_event_log_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_key", "version", name="uq_workspace_event_log_template_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    template_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Le colonne del file su cui e' stato costruito: per dire subito se un
    # file nuovo le ha tutte.
    columns_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceSource(WorkspaceBase):
    __tablename__ = "workspace_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_id", "ingestion_key", name="uq_workspace_source_ingestion"
        ),
        # Migrazione 0026 (P1.16): una fonte e' di un progetto o del cliente, e
        # le fonti del cliente si deduplicano dentro il cliente.
        CheckConstraint("project_id IS NOT NULL OR client_id IS NOT NULL", name="ck_workspace_sources_owner"),
        Index(
            "uq_workspace_source_client_ingestion",
            "tenant_id", "client_id", "ingestion_key",
            unique=True,
            postgresql_where=text("project_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    # Vuoto per le fonti del cliente (P1.16), che valgono per tutti i suoi progetti.
    project_id: Mapped[str | None] = mapped_column(ForeignKey("workspace_projects.id"), index=True)
    # Il cliente a cui la fonte appartiene: il suo, o quello del suo progetto.
    client_id: Mapped[str | None] = mapped_column(ForeignKey("workspace_clients.id"), index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    meta: Mapped[str] = mapped_column(String, nullable=False)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    retention: Mapped[str] = mapped_column(String, nullable=False, default="persistent")
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String, nullable=False, default="reference")
    # L'impronta del testo di questa fonte, dichiarata da chi l'ha scritta. Il
    # testo vive nella memoria episodica, non qui: questa colonna e' il segnale
    # di cambiamento, ed e' l'unica cosa che lo sweep dei piani indietro puo'
    # leggere senza caricare ogni intervista.
    #
    # NULL significa "non si sa", che non e' "vuota": le fonti registrate prima
    # di questa colonna non dichiarano niente, e l'identita' del set le tratta
    # come prima invece di inventare un'impronta che non hanno.
    #
    # Per un file caricato e' lo SHA-256 dei byte originali: lo stesso file
    # ricaricato nello stesso progetto ritrova la sua fonte invece di duplicarla.
    content_hash: Mapped[str | None] = mapped_column(String, index=True)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String)
    storage_key: Mapped[str | None] = mapped_column(String)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parser: Mapped[str | None] = mapped_column(String)
    ingestion_key: Mapped[str | None] = mapped_column(String)
    # L'acquisizione del file caricato, fatta dal worker (`source_worker`).
    # `None` per le fonti senza file (create dalla chat). `pending | done |
    # partial | failed`: niente `running`, la presa in carico e' una scadenza in
    # `acquisition_next_attempt_at`, come nella coda dei piani.
    acquisition_status: Mapped[str | None] = mapped_column(String)
    acquisition_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acquisition_next_attempt_at: Mapped[str | None] = mapped_column(String)
    acquisition_error: Mapped[str | None] = mapped_column(Text)
    # L'estrazione delle affermazioni ancorate (P1.12), dopo un gesto del
    # consulente: la conferma, o l'invio del file in chat. Stessa coda a scadenza
    # della lettura. `None` finche' nessuno l'ha chiesta.
    claims_status: Mapped[str | None] = mapped_column(String)
    claims_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_next_attempt_at: Mapped[str | None] = mapped_column(String)
    claims_error: Mapped[str | None] = mapped_column(Text)
    # Inviato in chat mentre era ancora in lettura: la conferma scatta a lettura finita.
    confirm_when_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Le affermazioni estratte vanno nel grafo (P1.14): Source -> Evidence ->
    # Claim nel canonical. Stessa coda a scadenza. `None` finche' non ce ne sono.
    graph_status: Mapped[str | None] = mapped_column(String)
    graph_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_next_attempt_at: Mapped[str | None] = mapped_column(String)
    graph_error: Mapped[str | None] = mapped_column(Text)
    # Il confronto con gli altri file del processo (P1.13), fra l'estrazione e
    # il grafo: le contraddizioni entrano nel grafo insieme alle affermazioni.
    reconcile_status: Mapped[str | None] = mapped_column(String)
    reconcile_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconcile_next_attempt_at: Mapped[str | None] = mapped_column(String)
    reconcile_error: Mapped[str | None] = mapped_column(Text)


class WorkspaceSourceEvidence(WorkspaceBase):
    """La rappresentazione canonica di una fonte: l'Evidence Bucket.

    Una riga per fonte, riscritta a ogni acquisizione. `content_hash` dice da
    quale versione del file viene: se il file cambia, queste evidenze descrivono
    un'altra versione e vanno riacquisite.
    """

    __tablename__ = "workspace_source_evidence"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_sources.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    parser: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    structure_json: Mapped[str] = mapped_column(Text, nullable=False)
    issues_json: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceSourceClaim(WorkspaceBase):
    """Un'affermazione di un file caricato, con la porzione che la sostiene.

    Senza porzione non esiste: e' la regola del Semantic Layer. La citazione e'
    controllata parola per parola sul testo della porzione (`quote_verified`).
    """

    __tablename__ = "workspace_source_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    segment_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_ref: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    extracted_at: Mapped[str] = mapped_column(String, nullable=False)
    # Il suo Claim nel grafo canonical, scritto dalla coda del grafo (P1.14).
    kg_claim_id: Mapped[str | None] = mapped_column(String)


class WorkspaceClaimRelation(WorkspaceBase):
    """Due affermazioni di file diversi sullo stesso fatto (P1.13).

    `corroboration`: dicono la stessa cosa. `divergence`: dicono altro, e
    `divergence_type` e' quello che le regole lasciano. Nessuna relazione si
    risolve da sola: resta visibile con le due affermazioni e le loro porzioni.
    """

    __tablename__ = "workspace_claim_relations"
    __table_args__ = (UniqueConstraint("claim_id", "other_claim_id", name="uq_claim_relations_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_source_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    other_claim_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_source_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    declared_type: Mapped[str | None] = mapped_column(String)
    divergence_type: Mapped[str | None] = mapped_column(String)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    kg_contradiction_id: Mapped[str | None] = mapped_column(String)


class WorkspaceEvidenceSegment(WorkspaceBase):
    """Una porzione citabile di una fonte, con la sua ancora (`Ordini!B7`, `#/texts/12`)."""

    __tablename__ = "workspace_evidence_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_sources.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_kind: Mapped[str] = mapped_column(String, nullable=False)
    anchor_ref: Mapped[str] = mapped_column(String, nullable=False)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String, nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False)


class WorkspacePlanMaterialization(WorkspaceBase):
    """La coda dei piani da ricostruire perche' la conoscenza e' cambiata.

    Il piano del processo nasceva quando il consulente chiedeva di disegnare: la
    sintesi - tre chiamate al modello - stava dentro il percorso critico di
    «Genera BPMN», che e' il momento peggiore per farla. Il lavoro appartiene al
    momento in cui **l'evidenza cambia**, non al momento in cui qualcuno guarda
    il risultato.

    Una riga per processo, e non una per evento: cinque interviste salvate di
    seguito non sono cinque sintesi da fare, sono una sintesi da fare dopo
    l'ultima. `requested_at` si sposta in avanti a ogni richiesta e il worker
    legge il set di fonti corrente quando arriva a lavorarla, quindi la coda non
    porta uno stato che potrebbe essere gia' vecchio.
    """

    __tablename__ = "workspace_plan_materializations"
    __table_args__ = (UniqueConstraint("tenant_id", "process_id", name="uq_plan_materialization_process"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    process_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # pending | done | failed. `running` non esiste: una passata che muore a
    # meta' deve tornare eleggibile da sola, e un lease che nessuno rilascia e'
    # il modo in cui una coda si blocca in silenzio.
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    requested_at: Mapped[str] = mapped_column(String, nullable=False)
    # Perche' la conoscenza e' cambiata: una fonte salvata, una rimossa. Serve a
    # leggere la coda, non a decidere: il set di fonti lo rilegge il worker.
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[str] = mapped_column(String, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(String)
    # Il piano prodotto dall'ultima passata riuscita: la versione e l'esito che
    # `ensure_process_plan` ha dichiarato (`synthesized`, `reused`, ...).
    last_action: Mapped[str | None] = mapped_column(String)
    plan_version: Mapped[int | None] = mapped_column(Integer)


class WorkspacePlanExtraction(WorkspaceBase):
    """Il piano parziale ricavato da una fonte: l'artefatto, non il ricordo.

    L'estrazione e' la chiamata piu' cara che facciamo, una per intervista a
    testo intero, e finora spariva dentro il merge: la quarta intervista di un
    processo costava quattro estrazioni invece di una, e ogni ricostruzione del
    piano rileggeva da capo anche cio' che nessuno aveva toccato.

    La riga vive per la **chiave**, non per il processo: due processi che
    leggono la stessa fonte, e una ricostruzione che ripassa sulla stessa
    intervista, trovano lo stesso artefatto. Nella chiave c'e' il tenant per
    costruzione (L8): due clienti con lo stesso documento non condividono mai un
    risultato, e il vincolo sta sia nella chiave sia nella colonna, perche' un
    riuso fra clienti dev'essere il prodotto di due difetti e non di uno.

    Non c'e' un contatore dei riusi: ogni colpo di cache lascia gia' una riga
    `cache_hit` nel registro dei consumi, ed e' li' che si legge quanto lavoro
    e' stato evitato. Due conti della stessa cosa divergono.
    """

    __tablename__ = "workspace_plan_extractions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "artifact_key", name="uq_plan_extraction_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    # L'identita' di cio' che il modello ha letto e di come l'ha letto: testo
    # esatto del prompt, versione del prompt, modello, livello di ragionamento.
    artifact_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Da quale fonte veniva, per poter leggere la tabella. Non e' nella chiave:
    # la stessa intervista rinominata e' lo stesso testo.
    source_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Le parti della chiave che vale la pena poter interrogare da sole: "quanto
    # ci e' costato il cambio di prompt" e' una domanda che si fa su queste.
    input_digest: Mapped[str] = mapped_column(String, nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String, nullable=False, default="")
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceSourceAudit(WorkspaceBase):
    """Il giudizio del revisore su una fonte, confrontata con un piano preciso.

    Stessa idea del piano parziale, un gradino dopo: il revisore di conformita'
    legge ogni fonte per intero contro gli elementi del piano, e ogni volta che
    il confronto si rifaceva - un canvas risalvato, una verifica chiesta di
    nuovo - rileggeva anche le fonti che niente aveva toccato.

    Si tiene il **verdetto grezzo** dell'agente, non i rilievi: la verifica delle
    citazioni nel testo e' deterministica e si rifa' ogni volta, cosi' un
    cambio in quella regola non lascia in magazzino rilievi verificati con la
    regola di prima.
    """

    __tablename__ = "workspace_source_audits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "artifact_key", name="uq_source_audit_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    # Fonte esatta come l'ha letta il revisore, elementi del piano, prompt,
    # modello, ragionamento, tenant.
    artifact_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String, nullable=False, default="")
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    verdict_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceDecision(WorkspaceBase):
    __tablename__ = "workspace_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id"), nullable=False, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class WorkspaceLlmUsage(WorkspaceBase):
    """Un evento di consumo per ogni chiamata al modello, riuscita o no.

    E' la tabella che risponde a «dove sono andati i soldi ieri». Le colonne
    sono le dimensioni con cui si legge quella risposta: per tenant, per
    operazione, per compito, per modello.

    Tre scelte che vale la pena non perdere:

    - una riga anche per i guasti e per i colpi di cache (`outcome`). Un timeout
      si paga, e una chiamata evitata e' il risultato migliore che possiamo
      avere: se non la registriamo non possiamo dimostrare di averla evitata;
    - `cost_estimate` puo' essere NULL, e non e' un difetto. Significa che il
      modello non ha un prezzo configurato. I token restano comunque contati;
    - `prompt_version` sta qui perche' un cambio di prompt cambia la spesa, e
      senza la versione non si riesce a dire quale cambio l'ha cambiata.
    """

    __tablename__ = "workspace_llm_usage"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="local", index=True)
    # L'operazione: tipo, identita' dell'esecuzione, e il lavoro a cui appartiene.
    operation_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    operation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_operation_id: Mapped[str | None] = mapped_column(String, index=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True)
    process_id: Mapped[str | None] = mapped_column(String, index=True)
    # Il compito e come e' stato eseguito.
    task: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model: Mapped[str] = mapped_column(String, nullable=False, index=True)
    prompt_version: Mapped[str | None] = mapped_column(String)
    reasoning_effort: Mapped[str | None] = mapped_column(String)
    # I token. `reasoning` e' un sottoinsieme di `output`, non un addendo: il
    # fornitore lo fattura come uscita. Sommarlo a parte gonfierebbe ogni stima.
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # `ok`, `timeout`, `error`, `cache_hit`, `refused`.
    outcome: Mapped[str] = mapped_column(String, nullable=False, index=True)
    error_kind: Mapped[str | None] = mapped_column(String)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Stringa decimale, non float: e' denaro, e un float non si somma due volte
    # allo stesso modo. NULL = modello senza prezzo configurato.
    cost_estimate: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # L'impronta sha256 del contesto di scope che il modello ha visto
    # (`context_budget.assemble`). NULL per i compiti che non lo ricevono.
    context_fingerprint: Mapped[str | None] = mapped_column(String, index=True)


def build_workspace_engine():
    return local_engine()


workspace_engine = build_workspace_engine()
WorkspaceSessionLocal = sessionmaker(bind=workspace_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def workspace_connection():
    session = WorkspaceSessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
