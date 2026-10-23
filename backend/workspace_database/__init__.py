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


def list_project_sources(project_id: str, *, include_client: bool = False) -> list[dict]:
    """Le fonti di un progetto e, con `include_client`, quelle del suo cliente.

    Una fonte del cliente (P1.16) vale per tutti i suoi progetti: compare nelle
    Fonti di ognuno, con `project_id` vuoto, e nel contesto degli agenti. Il
    default resta il solo progetto: il set di fonti di un piano di processo non
    le legge ancora, e cambiarlo qui l'avrebbe cambiato in silenzio.
    """
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            return []

        owned = WorkspaceSource.project_id == project_id
        if include_client:
            owned = or_(
                owned,
                and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == project.client_id),
            )
        statement = (
            select(WorkspaceSource)
            .where(owned)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .order_by(WorkspaceSource.name)
        )
        sources = session.execute(statement).scalars().all()
        return [source_to_dict(source) for source in sources]


def list_client_sources(client_id: str) -> list[dict] | None:
    """Le fonti del cliente: quelle che valgono per tutti i suoi progetti.

    Returns:
        Le fonti, o `None` se il cliente non esiste in questo tenant.
    """
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceClient, client_id) is None:
            return None
        sources = session.execute(
            select(WorkspaceSource)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .where(WorkspaceSource.project_id.is_(None))
            .where(WorkspaceSource.client_id == client_id)
            .order_by(WorkspaceSource.name)
        ).scalars().all()
        return [source_to_dict(source) for source in sources]


def get_project_source(source_id: str) -> dict | None:
    """La fonte, per id, dentro il tenant corrente.

    Args:
        source_id: Id della fonte, non affidabile.

    Returns:
        Il record della fonte, o ``None`` se non esiste in questo tenant.

    Sola lettura.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        return source_to_dict(source) if source is not None else None


def get_project_source_record(source_id: str) -> WorkspaceSource | None:
    """Restituisce una copia staccata della fonte, sempre limitata al tenant."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        session.expunge(source)
        return source


def _assert_source_scope(project_id: str, process_id: str | None) -> None:
    """Una fonte non puo' essere registrata fuori dallo scope del turno.

    L'evidenza raccolta in chat ha due destinazioni: la memoria episodica e il
    pannello Fonti. Isolare solo la prima lascerebbe il buco piu' visibile dei
    due - l'evidenza finisce nel processo giusto, ma la fonte compare nel
    pannello di un altro incarico, dove qualcuno la aprira' credendola sua.
    Qui il vincolo vale prima della scrittura, per ogni chiamante: il tool
    `save_process_evidence` deriva il progetto dal process_id che gli passa
    l'LLM, quindi controllare il solo progetto non basterebbe.

    No-op fuori da un agent run (worker, cutover, test).
    """
    from backend.agents.scope_guard import assert_process_in_scope, assert_project_in_scope

    assert_project_in_scope(project_id)
    assert_process_in_scope(process_id)


def _enqueue_plans_touched_by_source(
    session,
    *,
    project_id: str,
    process_id: str | None,
    tenant: str,
    reason: str,
) -> None:
    """Mette in coda i piani che questa fonte rende da rifare.

    Una fonte di progetto vale per ogni processo del progetto - e' cosi' che il
    registro dell'evidenza la legge - quindi il piano da rifare non e' uno solo.
    La coda si scrive nella stessa transazione della fonte: un piano da
    ricostruire che si perde perche' la transazione e' finita e' un piano che
    resta indietro in silenzio.
    """
    affected = (
        [process_id]
        if process_id
        else session.execute(
            select(WorkspaceProcess.id)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == tenant)
        )
        .scalars()
        .all()
    )
    for affected_process_id in affected:
        enqueue_plan_materialization(affected_process_id, reason=reason, session=session)


def create_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
    content_hash: str = "",
) -> dict:
    _assert_source_scope(project_id, process_id)
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if process_id:
            process = tenant_row(session, WorkspaceProcess, process_id)
            if process is None or process.project_id != project_id:
                raise ValueError(f"Processo non trovato: {process_id}")

        source_id = unique_id(session, WorkspaceSource, f"src-{slugify(name, 'source')}")
        source = WorkspaceSource(
            id=source_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            client_id=project.client_id,
            process_id=process_id,
            name=name.strip(),
            type=type.strip() or "Fonte",
            meta=meta.strip(),
            content_hash=content_hash.strip() or None,
        )
        session.add(source)
        session.flush()
        # La conoscenza del processo e' cambiata: il piano che descrive il
        # processo senza questa fonte e' da rifare. Va in coda qui, nella stessa
        # transazione della fonte, invece di essere ricostruito quando qualcuno
        # chiede di disegnare - che e' il momento in cui nessuno puo' aspettare.
        _enqueue_plans_touched_by_source(
            session,
            project_id=project_id,
            process_id=process_id,
            tenant=current_tenant_id,
            reason=f"fonte registrata: {source.name}",
        )
        return source_to_dict(source)


def process_id_for_identity(scopes: list[dict[str, str]]) -> str:
    """Il processo a cui un caricamento appartiene, per la sua identita'."""
    process_ids = sorted({item["id"].strip() for item in scopes if item.get("type") == "process"})
    return process_ids[0] if len(process_ids) == 1 else ""


def create_ingested_source(
    *,
    project_id: str | None = None,
    client_id: str | None = None,
    name: str,
    roles: list[str],
    retention: str,
    scopes: list[dict[str, str]],
    content_hash: str,
    byte_size: int,
    mime_type: str,
    storage_key: str,
) -> tuple[dict, bool]:
    """Registra una fonte caricata e la mette in coda per l'acquisizione.

    Il file e' gia' conservato (`storage_key`); leggerlo - layout, tabelle, OCR -
    lo fa `source_worker`, fuori dalla richiesta. Fino ad allora la fonte esiste
    ma non ha testo, e lo dice: `acquisition_status == "pending"`.

    Una fonte appartiene a un progetto (`project_id`) o al cliente
    (`client_id`, P1.16): quella del cliente vale per tutti i suoi progetti, non
    ha processo, e il suo ambito e' il cliente.
    """
    if (project_id is None) == (client_id is None):
        raise ValueError("Una fonte appartiene a un progetto o a un cliente, non a entrambi.")
    if client_id is not None:
        scopes = [{"type": "client", "id": client_id}]
    role_order = {name: index for index, name in enumerate(
        ("context", "process_evidence", "policy", "operational_data")
    )}
    scope_order = {"client": 0, "project": 1, "process": 2}
    role_values = sorted(set(roles), key=role_order.__getitem__)
    scopes_value = sorted(
        ({"type": scope_type, "id": scope_id} for scope_type, scope_id in {
            (item["type"], item["id"].strip()) for item in scopes
        }),
        key=lambda item: (scope_order[item["type"]], item["id"]),
    )
    roles_json = json.dumps(role_values, ensure_ascii=False, separators=(",", ":"))
    scopes_json = json.dumps(scopes_value, ensure_ascii=False, separators=(",", ":"))
    # L'identita' di un file caricato e' il suo contenuto, nel progetto e nel
    # processo a cui appartiene: i ruoli sono attributi che si cambiano, non
    # un'altra fonte. Prima entravano nella chiave, e lo stesso file con un
    # ruolo diverso diventava un doppione. Il processo invece resta: una fonte
    # appartiene a un solo processo, e lo stesso file portato in un altro
    # processo e' evidenza di quell'altro.
    ingestion_key = hashlib.sha256(
        f"file:{content_hash}:{process_id_for_identity(scopes)}".encode()
    ).hexdigest()
    process_ids = [item["id"] for item in scopes_value if item["type"] == "process"]
    # Con due processi la fonte finirebbe a livello di progetto (`process_id`
    # vuoto) e diventerebbe evidenza anche per un terzo processo che non c'entra.
    if len(process_ids) > 1:
        raise ValueError("Una fonte caricata appartiene a un solo processo.")
    process_id = process_ids[0] if process_ids else None
    if project_id is not None:
        _assert_source_scope(project_id, process_id)
        validate_source_scopes(project_id, scopes_value)

    with workspace_connection() as session:
        if project_id is not None:
            project = tenant_row(session, WorkspaceProject, project_id)
            if project is None:
                raise ValueError(f"Progetto non trovato: {project_id}")
            owner_client_id = project.client_id
            owned = WorkspaceSource.project_id == project_id
        else:
            if tenant_row(session, WorkspaceClient, client_id) is None:
                raise ValueError(f"Cliente non trovato: {client_id}")
            owner_client_id = client_id
            owned = and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == client_id)
        lock_key = int(ingestion_key[:16], 16)
        if lock_key >= 2**63:
            lock_key -= 2**64
        session.execute(select(func.pg_advisory_xact_lock(lock_key)))
        # Per contenuto e non per chiave: le fonti caricate prima di questa
        # regola hanno una chiave calcolata anche sui ruoli. Fra due doppioni
        # gia' esistenti vale il primo.
        existing = session.execute(
            select(WorkspaceSource)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .where(owned)
            .where(WorkspaceSource.content_hash == content_hash)
            .where(WorkspaceSource.storage_key.is_not(None))
            .where(
                WorkspaceSource.process_id == process_id
                if process_id
                else WorkspaceSource.process_id.is_(None)
            )
            .order_by(WorkspaceSource.id)
        ).scalars().first()
        if existing is not None:
            # Ricaricare un file che non era stato letto e' il modo naturale di
            # dire "riprova": la fonte torna in coda invece di restare morta.
            if existing.acquisition_status == "failed":
                existing.acquisition_status = "pending"
                existing.acquisition_attempts = 0
                existing.acquisition_error = None
                existing.acquisition_next_attempt_at = now_iso()
                existing.meta = "In lettura: testo ed evidenze arrivano tra poco."
                session.flush()
            return source_to_dict(existing), False

        source = WorkspaceSource(
            id=unique_id(session, WorkspaceSource, f"src-{slugify(name, 'source')}"),
            tenant_id=tenant_id(),
            project_id=project_id,
            client_id=owner_client_id,
            process_id=process_id,
            name=name.strip(),
            type="File",
            meta="In lettura: testo ed evidenze arrivano tra poco.",
            roles_json=roles_json,
            retention=retention,
            scopes_json=scopes_json,
            status="extracted",
            content_hash=content_hash,
            byte_size=byte_size,
            mime_type=mime_type,
            storage_key=storage_key,
            ingestion_key=ingestion_key,
            acquisition_status="pending",
            acquisition_attempts=0,
            acquisition_next_attempt_at=now_iso(),
        )
        session.add(source)
        session.flush()
        return source_to_dict(source), True


ACQUISITION_MAX_ATTEMPTS = 4


ACQUISITION_BACKOFF_SECONDS = 30


# Un PDF lungo con OCR resta in lettura per minuti: il lease copre la
# conversione piu' lenta attesa, non la media. Se chi l'ha presa muore, la
# fonte torna eleggibile da sola.
ACQUISITION_LEASE_SECONDS = 1200


def due_source_acquisitions(limit: int = 2, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti da leggere, di tutti i tenant.

    Come `due_plan_materializations`: `FOR UPDATE SKIP LOCKED` e scadenza spostata
    in avanti, cosi' due worker non leggono lo stesso file.

    Returns:
        Per ogni fonte: id, tenant, nome, storage_key e hash del contenuto.
    """
    now = now_iso()
    lease_until = (
        datetime.now(UTC) + timedelta(seconds=ACQUISITION_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.acquisition_status == "pending")
            .where(WorkspaceSource.acquisition_next_attempt_at <= now)
            .order_by(WorkspaceSource.acquisition_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        claimed = []
        for row in rows:
            # Il tentativo si conta alla presa in carico, non all'esito: un file
            # che fa morire il worker (memoria, processo ucciso) non arriva mai a
            # `fail_source_acquisition`, e senza questo tornerebbe in lettura a
            # ogni scadenza del lease, per sempre.
            if row.acquisition_attempts >= ACQUISITION_MAX_ATTEMPTS:
                row.acquisition_status = "failed"
                row.acquisition_next_attempt_at = None
                row.acquisition_error = row.acquisition_error or "La lettura si e' interrotta troppe volte."
                row.meta = f"Non leggibile: {row.acquisition_error}"[:2000]
                continue
            row.acquisition_attempts += 1
            row.acquisition_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "storage_key": row.storage_key,
                    "content_hash": row.content_hash,
                    "process_id": row.process_id,
                }
            )
        session.flush()
        return claimed


def complete_source_acquisition(source_id: str, parsed: "ParsedSource") -> dict | None:
    """Scrive il risultato della lettura: testo, evidenze ancorate, esito.

    `parsed` e' un `ParsedSource` di `source_ingestion`. Le evidenze precedenti
    della fonte vengono sostituite, non affiancate: descrivono lo stesso file.
    """
    evidence = parsed.evidence
    status = "partial" if evidence is not None and evidence.status == "partial" else "done"
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        source.extracted_text = parsed.text
        source.parser = parsed.parser
        source.acquisition_status = status
        source.acquisition_error = None
        source.acquisition_next_attempt_at = None
        if source.confirm_when_read and source.status != "approved":
            # Era partito in chat mentre era in lettura: la conferma scatta ora.
            _approve_source(session, source, reason=f"fonte inviata in chat: {source.name}")
        if status == "partial":
            missing = "; ".join(
                issue.message for issue in evidence.issues if issue.severity == "partial"
            )
            source.meta = f"Acquisizione parziale: {missing}"[:2000]
        else:
            source.meta = "Testo ed evidenze pronti per la consultazione."

        session.execute(
            delete(WorkspaceEvidenceSegment).where(WorkspaceEvidenceSegment.source_id == source_id)
        )
        session.execute(
            delete(WorkspaceSourceEvidence).where(WorkspaceSourceEvidence.source_id == source_id)
        )
        if evidence is not None:
            payload = evidence.to_dict()
            session.add(
                WorkspaceSourceEvidence(
                    source_id=source_id,
                    tenant_id=source.tenant_id,
                    schema_version=payload["schema_version"],
                    format=payload["format"],
                    parser=payload["parser"],
                    status=payload["status"],
                    content_hash=parsed.content_hash,
                    structure_json=json.dumps(payload["structure"], ensure_ascii=False),
                    issues_json=json.dumps(payload["issues"], ensure_ascii=False),
                    acquired_at=now_iso(),
                )
            )
            session.add_all(
                WorkspaceEvidenceSegment(
                    tenant_id=source.tenant_id,
                    source_id=source_id,
                    ordinal=ordinal,
                    anchor_kind=segment["anchor"]["kind"],
                    anchor_ref=segment["anchor"]["ref"],
                    locator_json=json.dumps(segment["anchor"]["locator"], ensure_ascii=False),
                    # PostgreSQL rifiuta il byte NUL nelle colonne di testo; un
                    # PDF o un foglio possono contenerlo.
                    text=segment["text"].replace("\x00", ""),
                    value_type=segment["value_type"],
                    value_json=json.dumps(segment["value"], ensure_ascii=False),
                    attributes_json=json.dumps(segment["attributes"], ensure_ascii=False),
                )
                for ordinal, segment in enumerate(payload["segments"])
            )
        session.flush()
        return source_to_dict(source)


def fail_source_acquisition(
    source_id: str,
    *,
    error: str,
    permanent: bool,
    max_attempts: int = ACQUISITION_MAX_ATTEMPTS,
    backoff_seconds: int = ACQUISITION_BACKOFF_SECONDS,
) -> dict | None:
    """Una lettura non riuscita.

    `permanent`: il file non e' leggibile (formato, password, XML non sicuro),
    riprovare dara' lo stesso esito. Altrimenti (servizio giu', timeout) si
    riprova con backoff, ma non per sempre.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        # Il tentativo e' gia' stato contato alla presa in carico.
        source.acquisition_error = str(error)[:2000]
        if permanent or source.acquisition_attempts >= max_attempts:
            source.acquisition_status = "failed"
            source.acquisition_next_attempt_at = None
            source.meta = f"Non leggibile: {error}"[:2000]
        else:
            delay = backoff_seconds * (2 ** (source.acquisition_attempts - 1))
            source.acquisition_next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
        session.flush()
        return source_to_dict(source)


class SourceNotVerifiable(ValueError):
    """La fonte non si puo' ancora usare come evidenza (in lettura o illeggibile)."""


def update_source_roles(source_id: str, roles: list[str]) -> dict | None:
    """Cambia a cosa serve una fonte. Non cambia quale fonte e'.

    Returns:
        La fonte aggiornata, o `None` se non c'e' in questo tenant.
    """
    role_order = {name: index for index, name in enumerate(
        ("context", "process_evidence", "policy", "operational_data")
    )}
    values = sorted(set(roles), key=role_order.__getitem__)
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        source.roles_json = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        session.flush()
        return source_to_dict(source)


def verify_project_source(source_id: str) -> dict | None:
    """Il consulente ha controllato il file: da adesso e' evidenza del processo.

    Un file caricato entra nel registro dell'evidenza solo dopo questa conferma
    (`status == "approved"`): il testo estratto da un parser non e' ancora una
    fonte che il consulente ha fatto propria. Come per una fonte registrata dalla
    chat, i piani dei processi che la fonte tocca vanno ricostruiti.

    Raises:
        SourceNotVerifiable: la lettura non e' finita o non e' riuscita.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        if source.storage_key and source.acquisition_status not in {"done", "partial"}:
            raise SourceNotVerifiable(
                "La fonte non è ancora stata letta: si può usare come evidenza quando la lettura è finita."
            )
        if source.status == "approved":
            return source_to_dict(source)
        _approve_source(session, source, reason=f"fonte verificata: {source.name}")
        session.flush()
        return source_to_dict(source)


def _approve_source(session: Any, source: WorkspaceSource, *, reason: str) -> None:
    """La fonte diventa evidenza: piani da ricostruire, affermazioni da estrarre.

    Il chiamante ha gia' controllato che la lettura sia finita.
    """
    source.status = "approved"
    source.confirm_when_read = False
    if source.process_id:
        affected = [source.process_id]
    elif source.project_id:
        affected = list(
            session.execute(
                select(WorkspaceProcess.id)
                .where(WorkspaceProcess.project_id == source.project_id)
                .where(WorkspaceProcess.tenant_id == source.tenant_id)
            ).scalars().all()
        )
    else:
        # Una fonte del cliente (P1.16) non e' ancora nel set di fonti dei
        # piani: confermarla non li rende vecchi.
        affected = []
    for affected_process_id in affected:
        enqueue_plan_materialization(affected_process_id, reason=reason, session=session)
    if source.storage_key and source.claims_status != "done":
        # P1.12: l'estrazione delle affermazioni parte da un gesto del
        # consulente - questa conferma - e mai da sola.
        source.claims_status = "pending"
        source.claims_attempts = 0
        source.claims_error = None
        source.claims_next_attempt_at = now_iso()


def confirm_sources_sent_in_chat(source_ids: list[str]) -> list[str]:
    """Mandare un file in chat vale come confermarlo.

    Un file gia' letto diventa evidenza subito; uno ancora in lettura lo
    diventa quando la lettura finisce (`confirm_when_read`). Uno non leggibile
    resta com'e'.

    Returns:
        Gli id delle fonti confermate adesso.
    """
    confirmed: list[str] = []
    with workspace_connection() as session:
        for source_id in dict.fromkeys(source_ids):
            source = tenant_row(session, WorkspaceSource, source_id)
            if source is None or not source.storage_key or source.status == "approved":
                continue
            if source.acquisition_status in {"done", "partial"}:
                _approve_source(session, source, reason=f"fonte inviata in chat: {source.name}")
                confirmed.append(source.id)
            elif source.acquisition_status == "pending":
                source.confirm_when_read = True
        session.flush()
    return confirmed


class SourceNotDiscardable(ValueError):
    """La fonte non si scarta: e' gia' evidenza del processo, o non e' un file caricato."""


def discard_uploaded_source(source_id: str) -> bool:
    """Scarta un file caricato che nessuno ha ancora fatto proprio.

    E' la regola della card nel composer: un file nuovo, caricato dalla chat e
    tolto prima dell'invio, non resta tra le Fonti. Una fonte confermata come
    evidenza (`status == "approved"`) o creata dalla chat senza file non si
    scarta da qui. Le evidenze della fonte cadono con lei (FK in cascata);
    l'originale su disco si toglie solo se nessun'altra fonte lo usa.

    Returns:
        `False` se la fonte non esiste nel tenant.

    Raises:
        SourceNotDiscardable: la fonte e' gia' evidenza o non ha un file.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return False
        if not source.storage_key or source.status == "approved":
            raise SourceNotDiscardable(
                "Questa fonte non si scarta da qui: e' gia' evidenza del processo o non e' un file caricato."
            )
        storage_key = source.storage_key
        session.execute(
            delete(WorkspaceEvidenceSegment).where(WorkspaceEvidenceSegment.source_id == source_id)
        )
        session.execute(
            delete(WorkspaceSourceEvidence).where(WorkspaceSourceEvidence.source_id == source_id)
        )
        session.delete(source)
        session.flush()
        still_used = session.execute(
            select(func.count())
            .select_from(WorkspaceSource)
            .where(WorkspaceSource.storage_key == storage_key)
        ).scalar_one()
    if not still_used:
        from backend.workspace_services.source_ingestion import SourceFileError, delete_original

        try:
            delete_original(storage_key)
        except (SourceFileError, OSError):
            logger.warning("originale %s non rimosso", storage_key, exc_info=True)
    return True


def source_acquisition_stats() -> dict[str, int]:
    """Quante fonti aspettano di essere lette e quante hanno smesso di riprovare."""
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceSource.acquisition_status, func.count())
            .where(WorkspaceSource.acquisition_status.is_not(None))
            .group_by(WorkspaceSource.acquisition_status)
        ).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0) + counts.get("partial", 0),
        "stuck": counts.get("failed", 0),
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


def validate_source_scopes(project_id: str, scopes: list[dict[str, str]]) -> None:
    """Impedisce che una fonte venga collegata a record di un altro incarico."""
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")
        for scope in scopes:
            if scope["type"] == "project" and scope["id"] != project_id:
                raise ValueError("L'ambito progetto non appartiene a questa fonte.")
            if scope["type"] == "client" and scope["id"] != project.client_id:
                raise ValueError("L'ambito cliente non appartiene a questo progetto.")
            if scope["type"] == "process":
                process = tenant_row(session, WorkspaceProcess, scope["id"])
                if process is None or process.project_id != project_id:
                    raise ValueError("Il processo scelto non appartiene a questo progetto.")


def ensure_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
    content_hash: str = "",
) -> tuple[dict, bool]:
    """Registra una fonte una volta sola, per nome, dentro il suo processo.

    Un'intervista salvata due volte dalla chat - il consulente riformula, il
    turno viene ripetuto - non deve diventare due voci nel pannello Fonti. Il
    record resta quello di prima: dice quando l'evidenza e' entrata nel
    progetto, e riscriverlo a ogni salvataggio cancellerebbe quel fatto.

    **Con una sola eccezione, ed e' il punto di questa funzione:** se il testo e'
    cambiato, la fonte non e' piu' la stessa fonte. L'impronta si aggiorna e i
    piani costruiti su di lei vanno in coda. Senza questo, un'intervista corretta
    e risalvata con lo stesso titolo lasciava l'identita' del set ferma, il piano
    risultava "costruito sulle fonti correnti" e continuava a descrivere il testo
    di prima: un piano indietro che nessun controllo poteva vedere.

    Args:
        project_id: Progetto proprietario, non affidabile.
        name: Nome della fonte come la legge il consulente, non affidabile.
        type: Etichetta del tipo, gia' tradotta per chi legge.
        meta: Nota in prosa sulla fonte.
        process_id: Processo a cui l'evidenza appartiene, quando c'e'.
        content_hash: L'impronta del testo salvato
            (`source_document.content_digest`). Vuota da chi il testo non ce
            l'ha: in quel caso l'impronta gia' registrata resta, perche'
            cancellarla direbbe "non si sa piu' cosa contiene" a proposito di
            una fonte che non e' cambiata.

    Returns:
        La fonte e se e' stata creata adesso (``False`` se esisteva gia', anche
        quando il suo testo e' stato aggiornato: la fonte non e' nuova).

    Raises:
        ValueError: Se il progetto non esiste o il processo non e' suo.
        ScopeViolation: Se progetto o processo non sono quelli autorizzati per
            il turno di chat corrente.

    Scrive nel workspace quando la fonte non esiste, o quando esiste e il suo
    testo e' cambiato.
    """
    _assert_source_scope(project_id, process_id)
    cleaned_name = name.strip()
    cleaned_hash = content_hash.strip()
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        existing = (
            session.execute(
                select(WorkspaceSource)
                .where(WorkspaceSource.project_id == project_id)
                .where(WorkspaceSource.tenant_id == current_tenant_id)
                .where(WorkspaceSource.process_id == process_id)
                .where(func.lower(WorkspaceSource.name) == cleaned_name.lower())
            )
            .scalars()
            .first()
        )
        if existing is not None:
            if cleaned_hash and cleaned_hash != (existing.content_hash or ""):
                existing.content_hash = cleaned_hash
                session.flush()
                _enqueue_plans_touched_by_source(
                    session,
                    project_id=project_id,
                    process_id=process_id,
                    tenant=current_tenant_id,
                    reason=f"testo della fonte cambiato: {existing.name}",
                )
            return source_to_dict(existing), False

    return (
        create_project_source(
            project_id=project_id,
            name=cleaned_name,
            type=type,
            meta=meta,
            process_id=process_id,
            content_hash=cleaned_hash,
        ),
        True,
    )


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
