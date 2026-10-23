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
from backend.workspace_database.evidence import (
    CLAIMS_BACKOFF_SECONDS,
    CLAIMS_LEASE_SECONDS,
    CLAIMS_MAX_ATTEMPTS,
    GRAPH_BACKOFF_SECONDS,
    GRAPH_LEASE_SECONDS,
    GRAPH_MAX_ATTEMPTS,
    MAX_RECONCILE_CANDIDATES,
    RECONCILE_BACKOFF_SECONDS,
    RECONCILE_LEASE_SECONDS,
    RECONCILE_MAX_ATTEMPTS,
    _claims_as_input,
    _queue_graph,
    _relations_touching,
    _sides,
    complete_source_claims,
    complete_source_graph,
    complete_source_reconcile,
    due_source_claims,
    due_source_graph,
    due_source_reconcile,
    fail_source_claims,
    fail_source_graph,
    fail_source_reconcile,
    graph_divergences,
    list_claim_relations,
    list_claims_for_sources,
    list_evidence_segments,
    list_source_claims,
    reconcile_inputs,
    record_graph_ids,
)
from backend.workspace_database.decisions import (
    create_project_decision,
    decision_to_dict,
    list_project_decisions,
)


logger = logging.getLogger(__name__)


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
