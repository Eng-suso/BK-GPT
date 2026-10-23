import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import and_, delete, func, or_, select

from backend.agents.chat_mode import assert_write_allowed
from backend.agents.run_context import BpmnVersionConflict, active_turn_writes
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnknown,
    quality_report_from_understanding,
    unknown_question_id,
)
from backend.security import get_current_tenant_id
from backend.workspace_defaults import (
    UNKNOWN_NEXT_STEP,
    UNKNOWN_OWNER,
    UNKNOWN_SECTOR,
    is_unknown_client_status,
    normalize_client_status,
    resolve_client_status,
    resolve_process_stage,
    resolve_process_status,
    resolve_project_phase,
    resolve_project_status,
)
from backend.workspace_milestones import merge_milestones, normalise_milestones
from backend.workspace_services.bpmn_review import build_bpmn_review_draft, bpmn_xml_from_review
from backend.workspace_services.bpmn_canvas_edit import optimize_bpmn_layout
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnReviewVersion,
    WorkspaceBpmnVersion,
    WorkspaceClaimRelation,
    WorkspaceClient,
    WorkspaceDecision,
    WorkspaceEventLog,
    WorkspaceEventLogPayload,
    WorkspacePlanExtraction,
    WorkspacePlanMaterialization,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    WorkspaceSimulationRunArtifact,
    WorkspaceSimulationRunLog,
    WorkspaceSimulationScenario,
    WorkspaceEvidenceSegment,
    WorkspaceSource,
    WorkspaceSourceAudit,
    WorkspaceSourceClaim,
    WorkspaceSourceEvidence,
    workspace_connection,
)


if TYPE_CHECKING:
    from backend.workspace_services.evidence.claims import ClaimsResult
    from backend.workspace_services.evidence.reconcile import ReconcileResult
    from backend.workspace_services.source_ingestion import ParsedSource
from backend.workspace_database._common import (
    decode_list,
    decode_milestones,
    encode_list,
    encode_milestones,
    normalize_name,
    now_iso,
    slugify,
    source_to_dict,
    tenant_id,
    tenant_row,
    unique_id,
)
from backend.workspace_database.registry import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    _clean_list,
    capped_limit,
    client_to_dict,
    clients_statement,
    count_clients,
    count_projects,
    create_client,
    create_process,
    create_project,
    fill_client_placeholders,
    get_process,
    get_project,
    list_clients,
    list_project_processes,
    list_projects,
    process_to_dict,
    project_to_dict,
    projects_statement,
    update_client,
    update_process,
    update_project,
)
from backend.workspace_database.conformance import (
    CONFORMANCE_FAILED,
    CONFORMANCE_LEASE_SECONDS,
    CONFORMANCE_MAX_ATTEMPTS,
    CONFORMANCE_UNAVAILABLE,
    ELEMENT_DECISIONS,
    _ElementDecisionRecord,
    _queue_conformance,
    conformance_queue_stats,
    conformance_state,
    decode_conformance_report,
    decode_element_decisions,
    due_conformance_checks,
    enqueue_unchecked_conformance,
    record_conformance_report,
    record_element_decision,
    release_conformance_check,
    request_conformance_check,
)
from backend.workspace_database.bpmn import (
    NO_PRECONDITION,
    _NoPrecondition,
    _assert_bpmn_not_changed_underneath,
    _canvas_xml_for_write,
    _latest_bpmn_version,
    _latest_bpmn_version_id,
    _remember_turn_write,
    bpmn_version_to_dict,
    create_bpmn_version,
    get_bpmn_model,
    list_bpmn_versions,
    restore_bpmn_version,
    update_bpmn_model,
)
from backend.workspace_database.reviews import (
    UnreadableReviewError,
    _KEEP_EVIDENCE_SOURCE_SET,
    _KeepExistingValue,
    _RECOMMENDATION_WAITING_ON_THE_USER,
    _assert_review_ready_for_approval,
    _is_canonical_semantic_model_payload,
    _mark_review_version_approved,
    _open_missing_information,
    _record_review_version,
    _review_artifacts,
    answer_bpmn_review_question,
    answered_unknowns,
    approve_bpmn_review,
    decode_answers,
    get_bpmn_review,
    get_bpmn_review_version,
    list_bpmn_review_versions,
    open_questions_with_answers,
    prepare_bpmn_review,
    review_approval_blockers,
    review_to_dict,
    review_version_to_dict,
    revise_bpmn_review,
    unanswered_questions,
    update_bpmn_review_brief,
)
from backend.workspace_database.plans import (
    MATERIALIZATION_BACKOFF_SECONDS,
    MATERIALIZATION_LEASE_SECONDS,
    MATERIALIZATION_MAX_ATTEMPTS,
    _materialization_to_dict,
    _owned_materialization,
    _plan_extraction_to_dict,
    complete_plan_materialization,
    due_plan_materializations,
    enqueue_plan_materialization,
    enqueue_stale_plan_materializations,
    fail_plan_materialization,
    plan_extractions_by_key,
    plan_materialization_for,
    plan_materialization_stats,
    save_plan_extraction,
    save_source_audit,
    source_audits_by_key,
)
from backend.workspace_database.sources import (
    ACQUISITION_BACKOFF_SECONDS,
    ACQUISITION_LEASE_SECONDS,
    ACQUISITION_MAX_ATTEMPTS,
    SourceNotDiscardable,
    SourceNotVerifiable,
    _approve_source,
    _assert_source_scope,
    _enqueue_plans_touched_by_source,
    complete_source_acquisition,
    confirm_sources_sent_in_chat,
    create_ingested_source,
    create_project_source,
    discard_uploaded_source,
    due_source_acquisitions,
    ensure_project_source,
    fail_source_acquisition,
    get_project_source,
    get_project_source_record,
    list_client_sources,
    list_project_sources,
    process_id_for_identity,
    source_acquisition_stats,
    update_source_roles,
    validate_source_scopes,
    verify_project_source,
)


logger = logging.getLogger(__name__)


#: Quanti altri file entrano al massimo nel confronto di una fonte (P1.13). Il
#: prompt ha gia' il suo tetto in caratteri (`reconcile.MAX_INPUT_CHARS`), ma una
#: fonte del cliente si confronta con tutti i file del cliente: senza un tetto
#: anche sulla lettura, un cliente grande li tirerebbe su tutti a ogni passata.
MAX_RECONCILE_CANDIDATES = 200


def decision_to_dict(decision: WorkspaceDecision) -> dict:
    return {
        "id": decision.id,
        "project_id": decision.project_id,
        "process_id": decision.process_id,
        "title": decision.title,
        "owner": decision.owner,
        "status": decision.status,
    }


CLAIMS_MAX_ATTEMPTS = 3


CLAIMS_BACKOFF_SECONDS = 60


# Un'estrazione lunga dura quanto il modello: il lease la copre intera.
CLAIMS_LEASE_SECONDS = 900


def due_source_claims(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti di cui estrarre le affermazioni.

    Come la lettura: il tentativo si conta alla presa in carico, cosi' una
    estrazione che fa cadere il worker non torna in coda per sempre.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=CLAIMS_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.claims_status == "pending")
            .where(WorkspaceSource.claims_next_attempt_at <= now)
            .order_by(WorkspaceSource.claims_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.claims_attempts >= CLAIMS_MAX_ATTEMPTS:
                row.claims_status = "failed"
                row.claims_next_attempt_at = None
                row.claims_error = row.claims_error or "L'estrazione si e' interrotta troppe volte."
                continue
            row.claims_attempts += 1
            row.claims_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "project_id": row.project_id,
                    "process_id": row.process_id,
                    "content_hash": row.content_hash,
                }
            )
        session.flush()
        return claimed


def complete_source_claims(source_id: str, result: "ClaimsResult", *, content_hash: str) -> int | None:
    """Scrive le affermazioni estratte, al posto di quelle di prima.

    `result` e' un `ClaimsResult` di `evidence.claims`.

    Returns:
        Quante affermazioni sono state scritte, o `None` se la fonte non c'e'.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        session.execute(delete(WorkspaceSourceClaim).where(WorkspaceSourceClaim.source_id == source_id))
        now = now_iso()
        session.add_all(
            WorkspaceSourceClaim(
                tenant_id=source.tenant_id,
                source_id=source_id,
                ordinal=ordinal,
                statement=claim.statement,
                segment_ordinal=claim.segment_ordinal,
                anchor_ref=claim.anchor_ref,
                quote=claim.quote.replace("\x00", ""),
                quote_verified=claim.quote_verified,
                content_hash=content_hash,
                prompt_version=result.prompt_version,
                extracted_at=now,
            )
            for ordinal, claim in enumerate(result.claims)
        )
        source.claims_status = "done"
        source.claims_next_attempt_at = None
        # P1.13: prima di andare nel grafo, le affermazioni nuove si
        # confrontano con quelle degli altri file del processo.
        source.reconcile_status = "pending"
        source.reconcile_attempts = 0
        source.reconcile_error = None
        source.reconcile_next_attempt_at = now
        # Fatto, ma non tutto: lo si dice invece di farlo credere completo.
        source.claims_error = (
            f"Lette le prime porzioni: {result.segments_left_out} rimaste fuori per la lunghezza."
            if result.segments_left_out
            else None
        )
        session.flush()
        return len(result.claims)


def fail_source_claims(source_id: str, *, error: str, permanent: bool) -> None:
    """Un'estrazione non riuscita: si riprova con backoff, ma non per sempre."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.claims_error = str(error)[:2000]
        if permanent or source.claims_attempts >= CLAIMS_MAX_ATTEMPTS:
            source.claims_status = "failed"
            source.claims_next_attempt_at = None
        else:
            delay = CLAIMS_BACKOFF_SECONDS * (2 ** max(0, source.claims_attempts - 1))
            source.claims_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


RECONCILE_MAX_ATTEMPTS = 3


RECONCILE_BACKOFF_SECONDS = 60


RECONCILE_LEASE_SECONDS = 900


def _queue_graph(source: WorkspaceSource) -> None:
    """La fonte entra nella coda del grafo (P1.14), che sostituisce cio' che c'era."""
    source.graph_status = "pending"
    source.graph_attempts = 0
    source.graph_error = None
    source.graph_next_attempt_at = now_iso()


def due_source_reconcile(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti da confrontare con gli altri file del processo.

    Il tentativo si conta alla presa in carico, come nelle altre code.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=RECONCILE_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.reconcile_status == "pending")
            .where(WorkspaceSource.reconcile_next_attempt_at <= now)
            .order_by(WorkspaceSource.reconcile_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
                row.reconcile_status = "failed"
                row.reconcile_next_attempt_at = None
                row.reconcile_error = row.reconcile_error or "Il confronto si e' interrotto troppe volte."
                # Il grafo non aspetta un confronto che non arrivera'.
                _queue_graph(row)
                continue
            row.reconcile_attempts += 1
            row.reconcile_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "project_id": row.project_id,
                    "process_id": row.process_id,
                }
            )
        session.flush()
        return claimed


def _claims_as_input(session, sources: list) -> list[dict]:
    # Righe ORM o tuple (`id`, `name`): servono solo quei due campi.
    names = {source.id: source.name for source in sources}
    if not names:
        return []
    rows = session.execute(
        select(WorkspaceSourceClaim)
        .where(WorkspaceSourceClaim.source_id.in_(list(names)))
        .order_by(WorkspaceSourceClaim.source_id, WorkspaceSourceClaim.ordinal)
    ).scalars().all()
    return [
        {"id": row.id, "statement": row.statement, "source_id": row.source_id, "source_name": names[row.source_id]}
        for row in rows
    ]


def reconcile_inputs(source_id: str) -> tuple[list[dict], list[dict]]:
    """Le affermazioni della fonte e quelle degli altri file con cui confrontarle.

    Gli altri file sono quelli confermati, gia' estratti, dello stesso progetto e
    dello stesso processo. Un file a livello di progetto (senza processo) si
    confronta con tutti i file del progetto, e tutti con lui. Le fonti del cliente
    (P1.16) valgono per tutti i suoi progetti: entrano nel confronto di ogni file
    del cliente, e una fonte del cliente si confronta con tutti.

    Returns:
        `(nuove, gia' presenti)`, entrambe con `id`, `statement`, `source_id`,
        `source_name`.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return [], []
        client_wide = and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == source.client_id)
        # Solo id e nome: la riga intera porta con se' il testo estratto.
        # In ordine di id, lo stesso in cui le affermazioni arrivano al prompt.
        others = (
            select(WorkspaceSource.id, WorkspaceSource.name)
            .where(WorkspaceSource.tenant_id == source.tenant_id)
            .where(WorkspaceSource.id != source.id)
            .where(WorkspaceSource.status == "approved")
            .where(WorkspaceSource.claims_status == "done")
        )
        if source.project_id is None:
            others = others.where(WorkspaceSource.client_id == source.client_id)
        else:
            same_project = WorkspaceSource.project_id == source.project_id
            if source.process_id:
                same_project = and_(
                    same_project,
                    or_(WorkspaceSource.process_id.is_(None), WorkspaceSource.process_id == source.process_id),
                )
            others = others.where(or_(same_project, client_wide))
        return (
            _claims_as_input(session, [source]),
            _claims_as_input(
                session,
                list(session.execute(others.order_by(WorkspaceSource.id).limit(MAX_RECONCILE_CANDIDATES)).all()),
            ),
        )


def complete_source_reconcile(source_id: str, result: "ReconcileResult") -> int | None:
    """Scrive le relazioni trovate, al posto di quelle di prima, e passa al grafo.

    Returns:
        Quante relazioni sono state scritte, o `None` se la fonte non c'e'.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        own = select(WorkspaceSourceClaim.id).where(WorkspaceSourceClaim.source_id == source_id)
        session.execute(delete(WorkspaceClaimRelation).where(WorkspaceClaimRelation.claim_id.in_(own)))
        now = now_iso()
        session.add_all(
            WorkspaceClaimRelation(
                tenant_id=source.tenant_id,
                project_id=source.project_id,
                process_id=source.process_id,
                claim_id=relation.claim_id,
                other_claim_id=relation.other_claim_id,
                kind=relation.kind,
                declared_type=relation.declared_type,
                divergence_type=relation.divergence_type,
                reasons_json=json.dumps(list(relation.reasons), ensure_ascii=False),
                explanation=relation.explanation,
                prompt_version=result.prompt_version,
                created_at=now,
            )
            for relation in result.relations
        )
        source.reconcile_status = "done"
        source.reconcile_next_attempt_at = None
        source.reconcile_error = (
            f"Confrontata con le prime affermazioni: {result.existing_left_out} rimaste fuori per la lunghezza."
            if result.existing_left_out
            else None
        )
        _queue_graph(source)
        session.flush()
        return len(result.relations)


def fail_source_reconcile(source_id: str, *, error: str, permanent: bool) -> None:
    """Un confronto non riuscito: si riprova con backoff, ma non per sempre.

    Quando si smette di riprovare, le affermazioni vanno comunque nel grafo:
    senza confronto, ma non ferme.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.reconcile_error = str(error)[:2000]
        if permanent or source.reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
            source.reconcile_status = "failed"
            source.reconcile_next_attempt_at = None
            _queue_graph(source)
        else:
            delay = RECONCILE_BACKOFF_SECONDS * (2 ** max(0, source.reconcile_attempts - 1))
            source.reconcile_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


def _relations_touching(session, source_id: str) -> list[WorkspaceClaimRelation]:
    own = select(WorkspaceSourceClaim.id).where(WorkspaceSourceClaim.source_id == source_id)
    return list(
        session.execute(
            select(WorkspaceClaimRelation)
            .where(or_(WorkspaceClaimRelation.claim_id.in_(own), WorkspaceClaimRelation.other_claim_id.in_(own)))
            .order_by(WorkspaceClaimRelation.id)
        ).scalars().all()
    )


def _sides(session, relation: WorkspaceClaimRelation, source_id: str):
    """Le due affermazioni della relazione: prima quella di `source_id`."""
    claim = session.get(WorkspaceSourceClaim, relation.claim_id)
    other = session.get(WorkspaceSourceClaim, relation.other_claim_id)
    return (claim, other) if claim.source_id == source_id else (other, claim)


def graph_divergences(source_id: str) -> list[dict]:
    """Le divergenze di questa fonte da portare nel grafo come contraddizioni.

    Una divergenza tocca due file: la scrive la coda del grafo del file che ci
    arriva per secondo, quando il Claim dell'altro esiste gia'. Per questo si
    guardano le relazioni in tutte e due le direzioni.

    Returns:
        Per ogni divergenza: `relation_id`, `ordinal` (l'affermazione di questa
        fonte), `other_kg_claim_id`, `divergence_type`, gli enunciati e i nomi
        dei due file.
    """
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        out = []
        for relation in _relations_touching(session, source_id):
            if relation.kind != "divergence":
                continue
            mine, theirs = _sides(session, relation, source_id)
            if not theirs.kg_claim_id:
                continue
            out.append(
                {
                    "relation_id": relation.id,
                    "ordinal": mine.ordinal,
                    "other_kg_claim_id": theirs.kg_claim_id,
                    "divergence_type": relation.divergence_type or "tension_to_explore",
                    "statement": mine.statement,
                    "other_statement": theirs.statement,
                    "source_name": session.get(WorkspaceSource, mine.source_id).name,
                    "other_source_name": session.get(WorkspaceSource, theirs.source_id).name,
                }
            )
        return out


def record_graph_ids(source_id: str, *, claim_ids: dict[int, str], contradiction_ids: dict[int, str]) -> None:
    """Annota i Claim e le contraddizioni che la coda del grafo ha scritto."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return
        for claim in session.execute(
            select(WorkspaceSourceClaim).where(WorkspaceSourceClaim.source_id == source_id)
        ).scalars():
            claim.kg_claim_id = claim_ids.get(claim.ordinal)
        for relation_id, contradiction_id in contradiction_ids.items():
            relation = session.get(WorkspaceClaimRelation, relation_id)
            if relation is not None:
                relation.kg_contradiction_id = contradiction_id
        session.flush()


def list_claim_relations(source_id: str) -> list[dict]:
    """Corroborazioni e divergenze di una fonte, ognuna con le due affermazioni.

    Ogni lato porta la sua porzione e la sua citazione: un conflitto si guarda
    con le due evidenze davanti, non con un riassunto.
    """
    from backend.memory.provenance import DIVERGENCE_LABEL_IT

    def side(claim: WorkspaceSourceClaim, source: WorkspaceSource) -> dict:
        return {
            "claim_id": claim.id,
            "source_id": source.id,
            "source_name": source.name,
            "statement": claim.statement,
            "anchor_ref": claim.anchor_ref,
            "quote": claim.quote,
            "quote_verified": claim.quote_verified,
        }

    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        out = []
        for relation in _relations_touching(session, source_id):
            mine, theirs = _sides(session, relation, source_id)
            out.append(
                {
                    "id": relation.id,
                    "kind": relation.kind,
                    "divergence_type": relation.divergence_type,
                    "divergence_label": DIVERGENCE_LABEL_IT.get(relation.divergence_type or ""),
                    "declared_type": relation.declared_type,
                    "reasons": json.loads(relation.reasons_json or "[]"),
                    "explanation": relation.explanation,
                    "claim": side(mine, session.get(WorkspaceSource, mine.source_id)),
                    "other": side(theirs, session.get(WorkspaceSource, theirs.source_id)),
                }
            )
        return out


GRAPH_MAX_ATTEMPTS = 3


GRAPH_BACKOFF_SECONDS = 60


GRAPH_LEASE_SECONDS = 120


def due_source_graph(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti le cui affermazioni vanno portate nel grafo.

    Il tentativo si conta alla presa in carico, come nelle altre code.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=GRAPH_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.graph_status == "pending")
            .where(WorkspaceSource.graph_next_attempt_at <= now)
            .order_by(WorkspaceSource.graph_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.graph_attempts >= GRAPH_MAX_ATTEMPTS:
                row.graph_status = "failed"
                row.graph_next_attempt_at = None
                row.graph_error = row.graph_error or "Il passaggio nel grafo si e' interrotto troppe volte."
                continue
            row.graph_attempts += 1
            row.graph_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "project_id": row.project_id,
                    "client_id": row.client_id,
                    "process_id": row.process_id,
                    "content_hash": row.content_hash,
                    "byte_size": row.byte_size,
                }
            )
        session.flush()
        return claimed


def complete_source_graph(source_id: str) -> None:
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.graph_status = "done"
        source.graph_next_attempt_at = None
        source.graph_error = None
        session.flush()


def fail_source_graph(source_id: str, *, error: str, permanent: bool) -> None:
    """Un passaggio nel grafo non riuscito: si riprova con backoff, ma non per sempre."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.graph_error = str(error)[:2000]
        if permanent or source.graph_attempts >= GRAPH_MAX_ATTEMPTS:
            source.graph_status = "failed"
            source.graph_next_attempt_at = None
        else:
            delay = GRAPH_BACKOFF_SECONDS * (2 ** max(0, source.graph_attempts - 1))
            source.graph_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


def list_source_claims(source_id: str) -> list[dict]:
    """Le affermazioni di una fonte, nell'ordine in cui sono state estratte."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        rows = session.execute(
            select(WorkspaceSourceClaim)
            .where(WorkspaceSourceClaim.source_id == source_id)
            .where(WorkspaceSourceClaim.tenant_id == tenant_id())
            .order_by(WorkspaceSourceClaim.ordinal)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "source_id": row.source_id,
                "ordinal": row.ordinal,
                "statement": row.statement,
                "segment_ordinal": row.segment_ordinal,
                "anchor_ref": row.anchor_ref,
                "quote": row.quote,
                "quote_verified": row.quote_verified,
                "extracted_at": row.extracted_at,
            }
            for row in rows
        ]


def list_claims_for_sources(source_ids: list[str]) -> list[dict]:
    """Le affermazioni di piu' fonti del tenant corrente, in una sola lettura."""
    if not source_ids:
        return []
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceSourceClaim)
            .where(WorkspaceSourceClaim.source_id.in_(source_ids))
            .where(WorkspaceSourceClaim.tenant_id == tenant_id())
            .order_by(WorkspaceSourceClaim.source_id, WorkspaceSourceClaim.ordinal)
        ).scalars().all()
        return [
            {"id": row.id, "statement": row.statement, "quote": row.quote,
             "quote_verified": row.quote_verified, "source_id": row.source_id}
            for row in rows
        ]


def list_evidence_segments(source_id: str) -> list[dict]:
    """Le porzioni citabili di una fonte, nell'ordine della fonte."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        rows = session.execute(
            select(WorkspaceEvidenceSegment)
            .where(WorkspaceEvidenceSegment.source_id == source_id)
            .where(WorkspaceEvidenceSegment.tenant_id == tenant_id())
            .order_by(WorkspaceEvidenceSegment.ordinal)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "source_id": row.source_id,
                "ordinal": row.ordinal,
                "kind": row.anchor_kind,
                "ref": row.anchor_ref,
                "locator": json.loads(row.locator_json),
                "text": row.text,
                "value_type": row.value_type,
                "value": json.loads(row.value_json) if row.value_json else None,
                "attributes": json.loads(row.attributes_json),
            }
            for row in rows
        ]


def list_project_decisions(project_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceDecision)
            .where(WorkspaceDecision.project_id == project_id)
            .where(WorkspaceDecision.tenant_id == tenant_id())
            .order_by(WorkspaceDecision.title)
        )
        decisions = session.execute(statement).scalars().all()
        return [decision_to_dict(decision) for decision in decisions]


def create_project_decision(
    project_id: str,
    title: str,
    owner: str = "Da assegnare",
    status: str = "Aperta",
    process_id: str | None = None,
) -> dict:
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if process_id:
            process = tenant_row(session, WorkspaceProcess, process_id)
            if process is None or process.project_id != project_id:
                raise ValueError(f"Processo non trovato: {process_id}")

        decision_id = unique_id(session, WorkspaceDecision, f"dec-{slugify(title, 'decision')}")
        decision = WorkspaceDecision(
            id=decision_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            process_id=process_id,
            title=title.strip(),
            owner=owner.strip() or "Da assegnare",
            status=status.strip() or "Aperta",
        )
        session.add(decision)
        session.flush()
        return decision_to_dict(decision)


# ---------------------------------------------------------------------------
# Ciclo di vita: chiudere non e' cancellare
#
# Un incarico finisce, e il record deve poter uscire dal lavoro corrente senza
# portarsi via decisioni, fonti e modelli. `archive` mette una data; `restore` la
# toglie; `delete` e' l'unica operazione che perde davvero qualcosa, e per questo
# dichiara prima cosa porta con se'.
# ---------------------------------------------------------------------------


def get_client_name(client_id: str) -> str | None:
    """Il nome del cliente, dentro il tenant corrente: e' la sua identita' nel canonical."""
    with workspace_connection() as session:
        client = tenant_row(session, WorkspaceClient, client_id)
        return client.name if client is not None else None


def _client_or_raise(session, client_id: str) -> WorkspaceClient:
    client = tenant_row(session, WorkspaceClient, client_id)
    if client is None:
        raise ValueError(f"Cliente non trovato: {client_id}")
    return client


def _project_or_raise(session, project_id: str) -> WorkspaceProject:
    project = tenant_row(session, WorkspaceProject, project_id)
    if project is None:
        raise ValueError(f"Progetto non trovato: {project_id}")
    return project


def _process_or_raise(session, process_id: str) -> WorkspaceProcess:
    process = tenant_row(session, WorkspaceProcess, process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")
    return process


def _record_counts(session, *, client=None, project=None) -> dict[str, int]:
    """Cosa sta appeso a questo record, contato sui dati.

    Serve a scrivere la conferma: "questo cliente porta con se' 3 progetti e 5
    processi" e' una frase che si puo' verificare, "sei sicuro?" no.
    """
    if client is not None:
        projects = list(client.projects)
    elif project is not None:
        projects = [project]
    else:
        projects = []

    processes = [process for item in projects for process in item.processes]
    project_ids = [item.id for item in projects]
    sources = 0
    decisions = 0

    if project_ids:
        sources = session.execute(
            select(func.count())
            .select_from(WorkspaceSource)
            .where(WorkspaceSource.project_id.in_(project_ids))
            .where(WorkspaceSource.tenant_id == tenant_id())
        ).scalar_one()
    if client is not None:
        sources += session.execute(
            select(func.count())
            .select_from(WorkspaceSource)
            .where(WorkspaceSource.project_id.is_(None))
            .where(WorkspaceSource.client_id == client.id)
            .where(WorkspaceSource.tenant_id == tenant_id())
        ).scalar_one()
        decisions = session.execute(
            select(func.count())
            .select_from(WorkspaceDecision)
            .where(WorkspaceDecision.project_id.in_(project_ids))
            .where(WorkspaceDecision.tenant_id == tenant_id())
        ).scalar_one()

    return {
        "projects": len(projects) if client is not None else 0,
        "processes": len(processes),
        "sources": int(sources),
        "decisions": int(decisions),
    }


def client_impact(client_id: str) -> dict:
    """Cosa comporta chiudere o eliminare questo cliente."""
    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        return {"id": client.id, "name": client.name, **_record_counts(session, client=client)}


def project_impact(project_id: str) -> dict:
    """Cosa comporta chiudere o eliminare questo progetto."""
    with workspace_connection() as session:
        project = _project_or_raise(session, project_id)
        counts = _record_counts(session, project=project)
        return {"id": project.id, "name": project.name, **counts}


def process_impact(process_id: str) -> dict:
    """Cosa comporta chiudere o eliminare questo processo."""
    with workspace_connection() as session:
        process = _process_or_raise(session, process_id)
        sources = session.execute(
            select(func.count())
            .select_from(WorkspaceSource)
            .where(WorkspaceSource.process_id == process.id)
            .where(WorkspaceSource.tenant_id == tenant_id())
        ).scalar_one()
        return {
            "id": process.id,
            "name": process.name,
            "projects": 0,
            "processes": 0,
            "sources": int(sources),
            "decisions": 0,
        }


def archive_client(client_id: str, reason: str | None = None) -> dict:
    """Chiude un cliente e, con lui, i suoi progetti e processi.

    Un cliente chiuso i cui progetti restassero aperti sarebbe uno stato che il
    consulente non puo' spiegare: l'archiviazione scende lungo la gerarchia, e
    `restore` la risale solo per cio' che era stato chiuso insieme.
    """
    assert_write_allowed("archiviare un cliente")
    stamp = now_iso()
    clean_reason = " ".join((reason or "").split()) or None

    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        if client.archived_at is not None:
            return client_to_dict(client)

        client.archived_at = stamp
        client.archive_reason = clean_reason

        for project in client.projects:
            if project.archived_at is None:
                project.archived_at = stamp
                project.archive_reason = clean_reason
                project.process_count = 0
                for process in project.processes:
                    if process.archived_at is None:
                        process.archived_at = stamp
                        process.archive_reason = clean_reason

        session.flush()
        return client_to_dict(client)


def restore_client(client_id: str) -> dict:
    """Riapre un cliente e cio' che era stato chiuso nello stesso momento."""
    assert_write_allowed("ripristinare un cliente")

    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        stamp = client.archived_at
        client.archived_at = None
        client.archive_reason = None

        for project in client.projects:
            if project.archived_at == stamp:
                project.archived_at = None
                project.archive_reason = None
                restored = 0
                for process in project.processes:
                    if process.archived_at == stamp:
                        process.archived_at = None
                        process.archive_reason = None
                    if process.archived_at is None:
                        restored += 1
                project.process_count = restored

        session.flush()
        return client_to_dict(client)


def archive_project(project_id: str, reason: str | None = None) -> dict:
    """Chiude un progetto e i suoi processi."""
    assert_write_allowed("archiviare un progetto")
    stamp = now_iso()
    clean_reason = " ".join((reason or "").split()) or None

    with workspace_connection() as session:
        project = _project_or_raise(session, project_id)
        if project.archived_at is not None:
            return project_to_dict(project)

        project.archived_at = stamp
        project.archive_reason = clean_reason
        project.process_count = 0
        for process in project.processes:
            if process.archived_at is None:
                process.archived_at = stamp
                process.archive_reason = clean_reason

        session.flush()
        return project_to_dict(project)


def restore_project(project_id: str) -> dict:
    """Riapre un progetto, e con lui il cliente se era chiuso."""
    assert_write_allowed("ripristinare un progetto")

    with workspace_connection() as session:
        project = _project_or_raise(session, project_id)
        stamp = project.archived_at
        project.archived_at = None
        project.archive_reason = None

        restored = 0
        for process in project.processes:
            if process.archived_at == stamp:
                process.archived_at = None
                process.archive_reason = None
            if process.archived_at is None:
                restored += 1
        project.process_count = restored

        # Un progetto attivo sotto un cliente chiuso non e' uno stato leggibile.
        if project.client.archived_at is not None:
            project.client.archived_at = None
            project.client.archive_reason = None

        session.flush()
        return project_to_dict(project)


def archive_process(process_id: str, reason: str | None = None) -> dict:
    """Chiude un processo, lasciando aperto il progetto."""
    assert_write_allowed("archiviare un processo")

    with workspace_connection() as session:
        process = _process_or_raise(session, process_id)
        if process.archived_at is None:
            process.archived_at = now_iso()
            process.archive_reason = " ".join((reason or "").split()) or None
            process.project.process_count = max(0, process.project.process_count - 1)
            session.flush()
        return process_to_dict(process)


def restore_process(process_id: str) -> dict:
    """Riapre un processo, e con lui il progetto se era chiuso."""
    assert_write_allowed("ripristinare un processo")

    with workspace_connection() as session:
        process = _process_or_raise(session, process_id)
        if process.archived_at is not None:
            process.archived_at = None
            process.archive_reason = None
            project = process.project
            if project.archived_at is not None:
                project.archived_at = None
                project.archive_reason = None
                project.process_count = 0
            if project.client.archived_at is not None:
                project.client.archived_at = None
                project.client.archive_reason = None
            project.process_count += 1
            session.flush()
        return process_to_dict(process)


def delete_client(client_id: str) -> dict:
    """Elimina un cliente e tutto cio' che ne dipende. Non si torna indietro.

    Prima l'evidenza nel cervello (GR-13), come in `delete_process`.
    """
    assert_write_allowed("eliminare un cliente")

    storage_keys: list[str] = []
    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        project_ids = [project.id for project in client.projects]
        client_name = client.name
        client_source_ids = list(
            session.execute(
                select(WorkspaceSource.id)
                .where(WorkspaceSource.tenant_id == tenant_id())
                .where(WorkspaceSource.project_id.is_(None))
                .where(WorkspaceSource.client_id == client_id)
            ).scalars()
        )
    from backend.memory.knowledge_graph import erase

    erase.erase_client_sources(client_name, client_source_ids)
    erase.erase_client(client_name, project_ids)

    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        removed = {"id": client.id, "name": client.name, **_record_counts(session, client=client)}
        for project in list(client.projects):
            storage_keys.extend(_purge_project(session, project))
        # Le fonti del cliente (P1.16): non stanno sotto nessun progetto.
        for source in session.execute(
            select(WorkspaceSource)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .where(WorkspaceSource.project_id.is_(None))
            .where(WorkspaceSource.client_id == client_id)
        ).scalars():
            if source.storage_key:
                storage_keys.append(source.storage_key)
            session.delete(source)
        session.flush()
        session.delete(client)
        session.flush()
    _remove_unreferenced_originals(storage_keys)
    return removed


def delete_project(project_id: str) -> dict:
    """Elimina un progetto, i suoi processi, fonti e decisioni.

    Prima l'evidenza nel cervello (GR-13), come in `delete_process`.
    """
    assert_write_allowed("eliminare un progetto")

    storage_keys: list[str] = []
    with workspace_connection() as session:
        _project_or_raise(session, project_id)
    from backend.memory.knowledge_graph import erase

    erase.erase_project(project_id)

    with workspace_connection() as session:
        project = _project_or_raise(session, project_id)
        removed = {
            "id": project.id,
            "name": project.name,
            **_record_counts(session, project=project),
        }
        storage_keys.extend(_purge_project(session, project))
        session.flush()
    _remove_unreferenced_originals(storage_keys)
    return removed


def delete_process(process_id: str) -> dict:
    """Elimina un processo, il suo modello BPMN e le fonti che vi puntavano.

    Prima l'evidenza nel cervello (GR-13, `knowledge_graph.erase`), poi il
    workspace: se la prima parte fallisce il processo resta e si puo' riprovare.
    Nell'ordine opposto l'evidenza resterebbe senza processo, pronta a tornare
    quando qualcuno ricrea un processo con lo stesso nome.
    """
    assert_write_allowed("eliminare un processo")

    storage_keys: list[str] = []
    with workspace_connection() as session:
        project_id = _process_or_raise(session, process_id).project_id
    from backend.memory.knowledge_graph import erase

    erase.erase_process(project_id, process_id)

    with workspace_connection() as session:
        process = _process_or_raise(session, process_id)
        removed = {
            "id": process.id,
            "name": process.name,
            "projects": 0,
            "processes": 1,
            "sources": 0,
            "decisions": 0,
        }
        project = process.project
        storage_keys.extend(_purge_process(session, process))
        if project.archived_at is None:
            project.process_count = max(0, project.process_count - 1)
        session.flush()
    _remove_unreferenced_originals(storage_keys)
    return removed


def _purge_process(session, process: WorkspaceProcess) -> list[str]:
    """Toglie un processo e tutto cio' che lo referenzia per id."""
    bpmn_model_id = process.bpmn_model_id

    # L'artefatto di simulazione ha una FK sul run: va tolto prima, o la
    # cancellazione del run lascia una riga orfana che nessuna query raggiunge.
    run_ids = [
        run.id
        for run in session.execute(
            select(WorkspaceSimulationRun).where(
                WorkspaceSimulationRun.bpmn_model_id == bpmn_model_id
            )
        ).scalars()
    ]
    if run_ids:
        for artifact in session.execute(
            select(WorkspaceSimulationRunArtifact).where(
                WorkspaceSimulationRunArtifact.run_id.in_(run_ids)
            )
        ).scalars():
            session.delete(artifact)
        for run_log in session.execute(
            select(WorkspaceSimulationRunLog).where(
                WorkspaceSimulationRunLog.run_id.in_(run_ids)
            )
        ).scalars():
            session.delete(run_log)
        # Fra run e artefatto non c'e' una relationship mappata: l'unita' di
        # lavoro non sa che l'artefatto va cancellato prima e puo' invertire
        # l'ordine, fermandosi sulla FK. Il flush fissa l'ordine.
        session.flush()

    storage_keys: list[str] = []
    for model, column in (
        (WorkspaceBpmnVersion, WorkspaceBpmnVersion.bpmn_model_id),
        (WorkspaceBpmnReview, WorkspaceBpmnReview.bpmn_model_id),
        (WorkspaceBpmnReviewVersion, WorkspaceBpmnReviewVersion.bpmn_model_id),
        (WorkspaceSimulationRun, WorkspaceSimulationRun.bpmn_model_id),
        (WorkspaceSimulationScenario, WorkspaceSimulationScenario.bpmn_model_id),
    ):
        for row in session.execute(select(model).where(column == bpmn_model_id)).scalars():
            session.delete(row)

    for model, column in (
        (WorkspaceSource, WorkspaceSource.process_id),
        (WorkspaceDecision, WorkspaceDecision.process_id),
    ):
        for row in session.execute(select(model).where(column == process.id)).scalars():
            if isinstance(row, WorkspaceSource) and row.storage_key:
                storage_keys.append(row.storage_key)
            session.delete(row)

    # Gli event log importati: prima il file, poi la riga, con lo stesso flush
    # che fissa l'ordine degli artefatti di simulazione.
    log_ids = list(session.execute(
        select(WorkspaceEventLog.id).where(WorkspaceEventLog.process_id == process.id)
    ).scalars())
    if log_ids:
        for payload in session.execute(
            select(WorkspaceEventLogPayload).where(WorkspaceEventLogPayload.event_log_id.in_(log_ids))
        ).scalars():
            session.delete(payload)
        session.flush()
        for log in session.execute(select(WorkspaceEventLog).where(WorkspaceEventLog.id.in_(log_ids))).scalars():
            session.delete(log)
        session.flush()

    session.delete(process)
    return storage_keys


def _purge_project(session, project: WorkspaceProject) -> list[str]:
    """Toglie un progetto, i suoi processi e i record che vi appartengono."""
    storage_keys: list[str] = []
    for process in list(project.processes):
        storage_keys.extend(_purge_process(session, process))

    for model, column in (
        (WorkspaceSource, WorkspaceSource.project_id),
        (WorkspaceDecision, WorkspaceDecision.project_id),
    ):
        for row in session.execute(select(model).where(column == project.id)).scalars():
            if isinstance(row, WorkspaceSource) and row.storage_key:
                storage_keys.append(row.storage_key)
            session.delete(row)

    session.delete(project)
    return storage_keys


def _remove_unreferenced_originals(storage_keys: list[str]) -> None:
    """Rimuove un blob dopo il commit, solo se nessun'altra fonte lo usa."""
    from backend.workspace_services.source_ingestion import SourceFileError, delete_original

    for storage_key in set(storage_keys):
        with workspace_connection() as session:
            still_used = session.execute(
                select(WorkspaceSource.id)
                .where(WorkspaceSource.tenant_id == tenant_id())
                .where(WorkspaceSource.storage_key == storage_key)
                .limit(1)
            ).scalar_one_or_none()
        if still_used is not None:
            continue
        try:
            delete_original(storage_key)
        except (SourceFileError, OSError):
            logger.warning("file originale non rimosso: %s", storage_key, exc_info=True)


def list_archive() -> dict:
    """Tutto cio' che e' stato chiuso, per la sezione Archivio."""
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        clients = session.execute(
            select(WorkspaceClient)
            .where(WorkspaceClient.tenant_id == current_tenant_id)
            .where(WorkspaceClient.archived_at.is_not(None))
            .order_by(WorkspaceClient.archived_at.desc())
        ).scalars().all()
        projects = session.execute(
            select(WorkspaceProject)
            .where(WorkspaceProject.tenant_id == current_tenant_id)
            .where(WorkspaceProject.archived_at.is_not(None))
            .order_by(WorkspaceProject.archived_at.desc())
        ).scalars().all()
        processes = session.execute(
            select(WorkspaceProcess)
            .where(WorkspaceProcess.tenant_id == current_tenant_id)
            .where(WorkspaceProcess.archived_at.is_not(None))
            .order_by(WorkspaceProcess.archived_at.desc())
        ).scalars().all()

        return {
            "clients": [client_to_dict(client) for client in clients],
            "projects": [project_to_dict(project, include_processes=False) for project in projects],
            "processes": [process_to_dict(process) for process in processes],
        }


def reset_workspace() -> None:
    storage_keys: list[str] = []
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        for model in (
            WorkspaceSource,
            WorkspaceDecision,
            WorkspaceSimulationRun,
            WorkspaceBpmnReview,
            WorkspaceBpmnVersion,
            WorkspaceBpmnModel,
            WorkspaceProcess,
            WorkspaceProject,
            WorkspaceClient,
        ):
            for row in session.execute(
                select(model).where(model.tenant_id == current_tenant_id)
            ).scalars():
                if isinstance(row, WorkspaceSource) and row.storage_key:
                    storage_keys.append(row.storage_key)
                session.delete(row)
    _remove_unreferenced_originals(storage_keys)
