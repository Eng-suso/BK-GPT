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
    WorkspacePlanExtraction,
    WorkspacePlanMaterialization,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    WorkspaceSimulationRunArtifact,
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


logger = logging.getLogger(__name__)

def encode_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def decode_list(value: str) -> list[str]:
    parsed = json.loads(value or "[]")
    return parsed if isinstance(parsed, list) else []


def decode_milestones(value: str) -> list[dict]:
    """Read the stored milestones, upgrading rows written as plain titles.

    Args:
        value: The project's stored ``milestones_json`` payload.

    Returns:
        list[dict]: The milestones as ``{title, status, completed_at}``.
    """
    return normalise_milestones(decode_list(value))


def encode_milestones(values: list[dict]) -> str:
    return json.dumps(values, ensure_ascii=False)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def tenant_id() -> str:
    return get_current_tenant_id()


def tenant_row(session, model, row_id: str):
    row = session.get(model, row_id)
    if row is None or getattr(row, "tenant_id", "local") != tenant_id():
        return None
    return row


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def unique_id(session, model, base_id: str) -> str:
    candidate = base_id
    suffix = 2

    while session.get(model, candidate) is not None:
        candidate = f"{base_id}-{suffix}"
        suffix += 1

    return candidate


def process_to_dict(process: WorkspaceProcess) -> dict:
    return {
        "id": process.id,
        "project_id": process.project_id,
        "bpmn_model_id": process.bpmn_model_id,
        "name": process.name,
        "stage": process.stage,
        "status": process.status,
        "owner": process.owner,
        "readiness": process.readiness,
        "archived_at": process.archived_at,
        "archive_reason": process.archive_reason,
    }


def project_to_dict(project: WorkspaceProject, include_processes: bool = True) -> dict:
    """Serialize a workspace project into a dictionary.
    
    Args:
        project: The workspace project to serialize.
        include_processes: Whether to include serialized process items in the
            result.
    
    Returns:
        A dictionary containing the project's tenant-scoped identifiers, client
        name, metadata, progress, list fields, and optionally its processes.
    """
    return {
        "id": project.id,
        "client_id": project.client_id,
        "client": project.client.name,
        "name": project.name,
        "objective": project.objective or "",
        "lead": project.lead,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "phase": project.phase,
        "status": project.status,
        "progress": project.progress,
        "processes": project.process_count,
        "next_step": project.next_step,
        "milestones": decode_milestones(project.milestones_json),
        "open_issues": decode_list(project.open_issues_json),
        "deliverables": decode_list(project.deliverables_json),
        "archived_at": project.archived_at,
        "archive_reason": project.archive_reason,
        "process_items": [
            process_to_dict(process)
            for process in project.processes
            if process.archived_at is None
        ]
        if include_processes
        else [],
    }


def client_to_dict(client: WorkspaceClient) -> dict:
    # I conteggi che il consulente legge sono quelli del lavoro corrente: un
    # progetto archiviato non e' un progetto in corso, e contarlo qui rimetterebbe
    # in pista un incarico chiuso.
    projects = [project for project in client.projects if project.archived_at is None]
    processes = [
        process.name
        for project in projects
        for process in project.processes
        if process.archived_at is None
    ]
    documents = [
        deliverable
        for project in projects
        for deliverable in decode_list(project.deliverables_json)
    ]
    next_activity = projects[0].next_step if projects else "Nessuna attivita aperta"

    return {
        "id": client.id,
        "name": client.name,
        "sector": client.sector,
        "status": client.status,
        "projects": len(projects),
        "next_activity": next_activity,
        "owner": client.owner,
        "contact": client.contact,
        "processes": processes,
        "documents": documents,
        "archived_at": client.archived_at,
        "archive_reason": client.archive_reason,
    }



#: Quante righe torna al massimo una lista senza che nessuno abbia chiesto un
#: numero. Non e' una paginazione: e' il tetto che impedisce a una richiesta di
#: tirare giu' il workspace intero, e sopra ci sta un conteggio, cosi' chi
#: guarda sa che ne mancano.
DEFAULT_LIST_LIMIT = 500
MAX_LIST_LIMIT = 2000


def capped_limit(limit: int | None) -> int:
    """Il numero di righe da chiedere: quello voluto, dentro i confini."""
    if limit is None:
        return DEFAULT_LIST_LIMIT
    return max(1, min(int(limit), MAX_LIST_LIMIT))


def clients_statement(include_archived: bool):
    statement = select(WorkspaceClient).where(WorkspaceClient.tenant_id == tenant_id())
    if not include_archived:
        statement = statement.where(WorkspaceClient.archived_at.is_(None))
    return statement


def count_clients(include_archived: bool = False) -> int:
    """Quanti clienti ci sono davvero, oltre quelli che la lista restituisce."""
    with workspace_connection() as session:
        return int(
            session.execute(
                select(func.count()).select_from(
                    clients_statement(include_archived).subquery()
                )
            ).scalar_one()
        )


def list_clients(include_archived: bool = False, limit: int | None = None) -> list[dict]:
    """List clients belonging to the current tenant in name order.

    Args:
        include_archived: Include closed clients. Off by default: the directory
            is the work in progress, not everything that ever happened.
        limit: Quante righe al massimo. Senza, vale `DEFAULT_LIST_LIMIT`: la
            query non aveva nessun tetto, quindi una sola richiesta poteva
            tirare giu' l'intero elenco di un cliente grosso.

    Returns:
        list[dict]: Tenant-scoped client records sorted by name.
    """
    with workspace_connection() as session:
        statement = (
            clients_statement(include_archived)
            .order_by(WorkspaceClient.name)
            .limit(capped_limit(limit))
        )
        clients = session.execute(statement).scalars().all()
        return [client_to_dict(client) for client in clients]


def fill_client_placeholders(
    client: WorkspaceClient,
    *,
    sector: str | None,
    status: str | None,
    owner: str | None,
    contact: str | None,
) -> None:
    """Fills only placeholder fields on a client without overwriting curated data.
    
    Args:
        client: Client record to update in memory.
        sector: Potentially untrusted sector value used when the current sector is
            empty or unknown.
        status: Potentially untrusted status value used when the current status is
            unknown.
        owner: Potentially untrusted owner value used when the current owner is
            empty or unknown.
        contact: Potentially untrusted contact value used when no contact exists.
    
    The function mutates the client object but does not commit or persist the
    changes.
    """
    if sector and client.sector in ("", UNKNOWN_SECTOR):
        client.sector = sector
    if status and is_unknown_client_status(client.status):
        client.status = status
    if owner and client.owner in ("", UNKNOWN_OWNER):
        client.owner = owner
    if contact and not client.contact:
        client.contact = contact


def create_client(
    name: str,
    sector: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    contact: str | None = None,
) -> dict:
    """Create or enrich a tenant-scoped client by normalized name.
    
    Args:
        name (str): Untrusted client name; must contain non-whitespace characters.
        sector (str | None): Untrusted sector value, when known.
        status (str | None): Untrusted client status, when known.
        owner (str | None): Untrusted owner value, when known.
        contact (str | None): Untrusted contact value, when known.
    
    Returns:
        dict: The newly created or existing client, including its persisted fields.
    
    Raises:
        ValueError: If ``name`` is empty or contains only whitespace.
    
    Side effects:
        Persists a new client, or enriches placeholder fields on an existing
        tenant-scoped client.
    """
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome cliente è obbligatorio.")

    stated_sector = (sector or "").strip() or None
    stated_status = normalize_client_status(status)
    stated_owner = (owner or "").strip() or None
    stated_contact = (contact or "").strip() or None

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing_clients = session.execute(
            select(WorkspaceClient).where(WorkspaceClient.tenant_id == current_tenant_id)
        ).scalars().all()
        existing_client = next(
            (
                client
                for client in existing_clients
                if normalize_name(client.name) == normalize_name(clean_name)
            ),
            None,
        )

        if existing_client is not None:
            fill_client_placeholders(
                existing_client,
                sector=stated_sector,
                status=stated_status,
                owner=stated_owner,
                contact=stated_contact,
            )
            session.flush()
            return client_to_dict(existing_client)

        client_id = unique_id(session, WorkspaceClient, slugify(clean_name, "client"))
        client = WorkspaceClient(
            id=client_id,
            tenant_id=current_tenant_id,
            name=clean_name,
            sector=stated_sector or UNKNOWN_SECTOR,
            status=resolve_client_status(stated_status),
            owner=stated_owner or UNKNOWN_OWNER,
            contact=stated_contact or "",
        )
        session.add(client)
        session.flush()
        return client_to_dict(client)


def projects_statement(include_archived: bool):
    statement = select(WorkspaceProject).where(WorkspaceProject.tenant_id == tenant_id())
    if not include_archived:
        statement = statement.where(WorkspaceProject.archived_at.is_(None))
    return statement


def count_projects(include_archived: bool = False) -> int:
    """Quanti incarichi ci sono davvero, oltre quelli che la lista restituisce."""
    with workspace_connection() as session:
        return int(
            session.execute(
                select(func.count()).select_from(
                    projects_statement(include_archived).subquery()
                )
            ).scalar_one()
        )


def list_projects(include_archived: bool = False, limit: int | None = None) -> list[dict]:
    """Gli incarichi dello spazio di lavoro, in ordine di nome.

    Args:
        include_archived: Include gli incarichi chiusi. Spento di default.
        limit: Quante righe al massimo. Senza, vale `DEFAULT_LIST_LIMIT`.
    """
    with workspace_connection() as session:
        statement = (
            projects_statement(include_archived)
            .order_by(WorkspaceProject.name)
            .limit(capped_limit(limit))
        )
        projects = session.execute(statement).scalars().all()
        return [project_to_dict(project) for project in projects]


def create_project(
    client_id: str,
    name: str,
    objective: str | None = None,
    lead: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    progress: int = 0,
    next_step: str | None = None,
    milestones: list | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> dict:
    """Create and persist a tenant-scoped project for an existing client.
    
    Args:
        client_id (str): Untrusted client identifier that must belong to the current tenant.
        name (str): Untrusted project name; must contain non-whitespace characters.
        objective (str | None): Untrusted project objective.
        lead (str | None): Untrusted engagement lead. Left unset when not declared:
            il placeholder lo mette chi legge, non il record.
        start_date (str | None): Untrusted ISO start date, already validated at the
            Pydantic boundary.
        end_date (str | None): Untrusted ISO end date, already validated at the
            Pydantic boundary.
        phase (str | None): Untrusted project phase, resolved to the configured placeholder when omitted.
        status (str | None): Untrusted project status, resolved to the configured placeholder when omitted.
        progress (int): Untrusted progress value, constrained to the range 0 through 100.
        next_step (str | None): Untrusted next step, replaced with the configured placeholder when empty.
        milestones (list | None): Untrusted milestone entries to store with the project, as titles or as ``{title, status, completed_at}`` mappings.
        open_issues (list[str] | None): Untrusted open-issue entries to store with the project.
        deliverables (list[str] | None): Untrusted deliverable entries to store with the project.
    
    Returns:
        dict: The persisted project serialized as a dictionary.
    
    Raises:
        ValueError: If the name is empty, the client does not exist in the current tenant, or progress cannot be converted to an integer.
    
    Side Effects:
        Persists the project in the workspace database.
    """
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome progetto è obbligatorio.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        client = tenant_row(session, WorkspaceClient, client_id)

        if client is None:
            raise ValueError(f"Cliente non trovato: {client_id}")

        project_id = unique_id(session, WorkspaceProject, slugify(clean_name, "project"))
        project = WorkspaceProject(
            id=project_id,
            tenant_id=current_tenant_id,
            client_id=client_id,
            name=clean_name,
            objective=(objective or "").strip(),
            lead=(lead or "").strip() or None,
            start_date=(start_date or "").strip() or None,
            end_date=(end_date or "").strip() or None,
            phase=resolve_project_phase(phase),
            status=resolve_project_status(status),
            progress=max(0, min(int(progress), 100)),
            process_count=0,
            next_step=(next_step or "").strip() or UNKNOWN_NEXT_STEP,
            milestones_json=encode_milestones(normalise_milestones(milestones)),
            open_issues_json=encode_list(open_issues or []),
            deliverables_json=encode_list(deliverables or []),
        )
        session.add(project)
        session.flush()
        return project_to_dict(project)


def update_client(
    client_id: str,
    name: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    contact: str | None = None,
) -> dict:
    """Update the specified fields of a tenant-owned client.
    
    Args:
        client_id (str): Untrusted client identifier.
        name (str | None): Untrusted replacement name; must contain non-whitespace
            text when provided.
        sector (str | None): Untrusted replacement sector. Blank values use the
            unknown-sector placeholder.
        status (str | None): Untrusted replacement status.
        owner (str | None): Untrusted replacement owner. Blank values use the
            unassigned-owner placeholder.
        contact (str | None): Untrusted replacement contact value. Blank values are
            stored as an empty string.
    
    Returns:
        dict: The updated client serialized as a dictionary.
    
    Raises:
        ValueError: If the client does not belong to the current tenant, does not
            exist, or a provided name is empty after trimming.
    
    Side Effects:
        Persists the supplied changes to the tenant's client record. Fields
        whose values are None remain unchanged.
    """
    with workspace_connection() as session:
        client = tenant_row(session, WorkspaceClient, client_id)

        if client is None:
            raise ValueError(f"Cliente non trovato: {client_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Il nome cliente è obbligatorio.")
            client.name = clean_name
        if sector is not None:
            client.sector = sector.strip() or UNKNOWN_SECTOR
        if status is not None:
            client.status = resolve_client_status(status)
        if owner is not None:
            client.owner = owner.strip() or UNKNOWN_OWNER
        if contact is not None:
            client.contact = contact.strip()

        session.flush()
        return client_to_dict(client)


def update_project(
    project_id: str,
    name: str | None = None,
    client_id: str | None = None,
    objective: str | None = None,
    lead: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    progress: int | None = None,
    next_step: str | None = None,
    milestones: list | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> dict:
    """Update the specified fields of a tenant-owned project and persist the changes.
    
    A value of ``None`` leaves its field unchanged. List arguments replace the
    corresponding stored lists, including when an empty list is supplied. Project
    names must be non-empty after trimming, client references must belong to the
    current tenant, and progress is constrained to the range 0–100.
    
    Args:
        project_id: Untrusted project identifier.
        name: Untrusted replacement project name.
        client_id: Untrusted replacement client identifier.
        objective: Untrusted replacement project objective.
        phase: Untrusted replacement project phase.
        status: Untrusted replacement project status.
        progress: Untrusted replacement progress value.
        next_step: Untrusted replacement next step.
        milestones: Untrusted replacement milestone list, as titles or as
            ``{title, status, completed_at}`` mappings. An entry sent as a plain
            title keeps the state it already had.
        open_issues: Untrusted replacement open-issue list.
        deliverables: Untrusted replacement deliverable list.
    
    Returns:
        A dictionary containing the updated project.
    
    Raises:
        ValueError: If the project or replacement client does not exist, or if the
            replacement name is empty after trimming.
    """
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)

        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Il nome progetto è obbligatorio.")
            project.name = clean_name
        if client_id is not None and client_id != project.client_id:
            client = tenant_row(session, WorkspaceClient, client_id)
            if client is None:
                raise ValueError(f"Cliente non trovato: {client_id}")
            project.client_id = client_id
        if objective is not None:
            project.objective = objective.strip()
        # Stringa vuota qui e' "l'ho cancellato", non "non l'ho detto": il form
        # svuota un campo mandandolo vuoto, e il record deve poterlo dimenticare.
        if lead is not None:
            project.lead = lead.strip() or None
        if start_date is not None:
            project.start_date = start_date.strip() or None
        if end_date is not None:
            project.end_date = end_date.strip() or None
        if phase is not None:
            project.phase = resolve_project_phase(phase)
        if status is not None:
            project.status = resolve_project_status(status)
        if progress is not None:
            project.progress = max(0, min(int(progress), 100))
        if next_step is not None:
            project.next_step = next_step.strip() or UNKNOWN_NEXT_STEP
        if milestones is not None:
            project.milestones_json = encode_milestones(
                merge_milestones(decode_milestones(project.milestones_json), milestones)
            )
        if open_issues is not None:
            project.open_issues_json = encode_list(_clean_list(open_issues))
        if deliverables is not None:
            project.deliverables_json = encode_list(_clean_list(deliverables))

        session.flush()
        return project_to_dict(project)


def _clean_list(values: list[str]) -> list[str]:
    """
    Clean list entries by removing blank values and normalizing whitespace.
    
    Args:
        values: Untrusted string values to clean.
    
    Returns:
        A list containing non-blank entries with consecutive whitespace collapsed.
    """
    return [" ".join(str(value).split()) for value in values if str(value).strip()]


def get_project(project_id: str) -> dict | None:
    """Retrieve a project belonging to the current tenant.
    
    Args:
        project_id (str): Untrusted project identifier to look up within the current tenant.
    
    Returns:
        dict | None: A dictionary representation of the project, or None when no matching
            tenant-owned project exists.
    """
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        return project_to_dict(project) if project else None


def list_project_processes(project_id: str, include_archived: bool = False) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceProcess)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == tenant_id())
            .order_by(WorkspaceProcess.name)
        )
        if not include_archived:
            statement = statement.where(WorkspaceProcess.archived_at.is_(None))
        processes = session.execute(statement).scalars().all()
        return [process_to_dict(process) for process in processes]


def create_process(
    project_id: str,
    name: str,
    stage: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    readiness: int = 0,
) -> dict:
    """Create a tenant-scoped process and its associated empty BPMN model.
    
    The process name is trimmed and must be non-empty. Stage, status, and owner
    use configured placeholders when unspecified, and readiness is constrained to
    the range 0–100. The project must belong to the current tenant. This function
    persists both records and updates the project's process count.
    
    Args:
        project_id (str): Untrusted project identifier.
        name (str): Untrusted process name.
        stage (str | None): Untrusted process stage, or None to use its placeholder.
        status (str | None): Untrusted process status, or None to use its placeholder.
        owner (str | None): Untrusted process owner, or None to use its placeholder.
        readiness (int): Untrusted readiness value, constrained to 0–100.
    
    Returns:
        dict: The serialized newly created process.
    
    Raises:
        ValueError: If the name is blank, the project does not exist in the current
            tenant, or readiness cannot be converted to an integer.
        TypeError: If readiness cannot be converted to an integer because of its
            type.
    """
    clean_name = name.strip()

    if not clean_name:
        raise ValueError("Il nome processo è obbligatorio.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        project = tenant_row(session, WorkspaceProject, project_id)

        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        process_id = unique_id(session, WorkspaceProcess, slugify(clean_name, "process"))
        bpmn_model_id = unique_id(session, WorkspaceBpmnModel, f"{process_id}-bpmn")
        process = WorkspaceProcess(
            id=process_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            bpmn_model_id=bpmn_model_id,
            name=clean_name,
            stage=resolve_process_stage(stage),
            status=resolve_process_status(status),
            owner=(owner or "").strip() or UNKNOWN_OWNER,
            readiness=max(0, min(int(readiness), 100)),
        )
        session.add(process)
        session.add(
            WorkspaceBpmnModel(
                id=bpmn_model_id,
                tenant_id=current_tenant_id,
                process_id=process_id,
                name=f"{process.name} BPMN",
                xml=None,
            )
        )
        session.flush()
        project.process_count = session.scalar(
            select(func.count())
            .select_from(WorkspaceProcess)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == current_tenant_id)
        ) or 0
        return process_to_dict(process)


def update_process(
    process_id: str,
    name: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    readiness: int | None = None,
) -> dict:
    """Update selected fields of a tenant-owned process and persist the changes.
    
    A process rename also updates the associated BPMN model name. Readiness is
    constrained to the range 0–100, and omitted fields retain their existing
    values.
    
    Args:
        process_id (str): Untrusted process identifier.
        name (str | None): Untrusted replacement name; must contain non-whitespace
            text when provided.
        stage (str | None): Untrusted replacement process stage.
        status (str | None): Untrusted replacement process status.
        owner (str | None): Untrusted replacement owner; blank values use the
            configured unknown-owner placeholder.
        readiness (int | None): Untrusted replacement readiness value, constrained
            to 0–100.
    
    Returns:
        dict: The updated process serialized as a dictionary.
    
    Raises:
        ValueError: If the process does not exist for the current tenant, the
            provided name is blank, or readiness cannot be converted to an integer.
    """
    with workspace_connection() as session:
        process = tenant_row(session, WorkspaceProcess, process_id)

        if process is None:
            raise ValueError(f"Processo non trovato: {process_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Il nome processo è obbligatorio.")
            process.name = clean_name
            model = tenant_row(session, WorkspaceBpmnModel, process.bpmn_model_id)
            if model is not None:
                model.name = f"{clean_name} BPMN"
        if stage is not None:
            process.stage = resolve_process_stage(stage)
        if status is not None:
            process.status = resolve_process_status(status)
        if owner is not None:
            process.owner = owner.strip() or UNKNOWN_OWNER
        if readiness is not None:
            process.readiness = max(0, min(int(readiness), 100))

        session.flush()
        return process_to_dict(process)


def get_process(process_id: str) -> dict | None:
    """Retrieve a process belonging to the current tenant.
    
    Args:
        process_id (str): Untrusted process identifier to look up within the current tenant.
    
    Returns:
        dict | None: The serialized process, or None if no matching tenant-owned process exists.
    """
    with workspace_connection() as session:
        process = tenant_row(session, WorkspaceProcess, process_id)
        return process_to_dict(process) if process else None


def get_bpmn_model(bpmn_model_id: str) -> dict | None:
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
            "version_id": _latest_bpmn_version_id(session, model.id),
        }


def _latest_bpmn_version(session, bpmn_model_id: str) -> WorkspaceBpmnVersion | None:
    statement = (
        select(WorkspaceBpmnVersion)
        .where(WorkspaceBpmnVersion.bpmn_model_id == bpmn_model_id)
        .where(WorkspaceBpmnVersion.tenant_id == tenant_id())
        .order_by(WorkspaceBpmnVersion.id.desc())
        .limit(1)
    )
    return session.execute(statement).scalars().first()


def _latest_bpmn_version_id(session, bpmn_model_id: str) -> int | None:
    latest = _latest_bpmn_version(session, bpmn_model_id)
    return latest.id if latest is not None else None


class _NoPrecondition:
    """Chi scrive non ha detto da quale versione parte (chiamanti interni)."""


NO_PRECONDITION = _NoPrecondition()


def _assert_bpmn_not_changed_underneath(
    session,
    bpmn_model_id: str,
    expected_version_id: int | None | _NoPrecondition,
) -> None:
    """Rifiuta una scrittura che cancellerebbe una versione che chi scrive non ha visto.

    Due controlli, indipendenti:
    - `expected_version_id`: chi salva a mano dice da quale versione e' partito.
      `None` vuol dire "da nessuna": il modello non aveva ancora versioni, e se
      ora ne ha una e' di qualcun altro. `NO_PRECONDITION` salta il controllo;
    - il registro del turno: dentro un agent run, una versione nata dopo
      l'inizio del turno e non scritta dal turno e' di qualcun altro.

    Va chiamata con la riga del modello gia' bloccata (`FOR UPDATE`), o due
    scritture concorrenti passerebbero entrambe il controllo.
    """
    latest = _latest_bpmn_version(session, bpmn_model_id)
    latest_id = latest.id if latest is not None else None
    if not isinstance(expected_version_id, _NoPrecondition) and latest_id != expected_version_id:
        raise BpmnVersionConflict(
            "Il diagramma e' stato salvato da un'altra parte dopo che lo hai aperto. "
            "Ricarica il canvas per vedere l'ultima versione prima di salvare."
        )

    turn = active_turn_writes()
    if turn is None or latest is None:
        return
    if bpmn_model_id in turn.base_version_by_model:
        # L'XML su cui lavora l'agente viene da una versione nota - o da
        # nessuna, il diagramma iniziale: vale quella, anche se l'altra
        # scrittura e' arrivata prima dell'inizio del turno (una scheda rimasta
        # aperta su una versione vecchia, o due canvas su un processo nuovo).
        changed = latest.id != turn.base_version_by_model[bpmn_model_id]
    else:
        changed = latest.id not in turn.written_version_ids and latest.created_at > turn.started_at
    if changed:
        raise BpmnVersionConflict(
            "Il consulente ha salvato il diagramma mentre lavoravi: la tua modifica "
            "lo sovrascriverebbe. Non e' stata salvata. Prima rileggi il canvas "
            "salvato, poi rifai la modifica su quella versione."
        )


def _remember_turn_write(bpmn_model_id: str, version_id: int) -> None:
    """La versione appena scritta dal turno diventa la sua nuova base."""
    turn = active_turn_writes()
    if turn is not None:
        turn.written_version_ids.add(version_id)
        turn.base_version_by_model[bpmn_model_id] = version_id


def bpmn_version_to_dict(version: WorkspaceBpmnVersion) -> dict:
    return {
        "id": version.id,
        "bpmn_model_id": version.bpmn_model_id,
        "process_id": version.process_id,
        "xml": version.xml,
        "change_summary": version.change_summary,
        "source": version.source,
        "created_at": version.created_at,
    }


def create_bpmn_version(
    session,
    model: WorkspaceBpmnModel,
    xml: str,
    change_summary: str,
    source: str,
) -> WorkspaceBpmnVersion:
    """Create and stage a BPMN version snapshot for a model.
    
    Args:
        session: SQLAlchemy session used to stage the new version.
        model (WorkspaceBpmnModel): Model associated with the version.
        xml (str): Untrusted BPMN XML content to store.
        change_summary (str): Untrusted description of the change; blank values use a default.
        source (str): Untrusted version source; blank values use ``"manual"``.
    
    Returns:
        WorkspaceBpmnVersion: The newly created, unsaved version entity.
    
    Raises:
        AuthorizationError: If the current user is not permitted to write BPMN data.
    
    The version inherits the model's tenant, model, and process identifiers. The entity is added to
    the session but is not committed.
    """
    assert_write_allowed("create_bpmn_version")
    version = WorkspaceBpmnVersion(
        tenant_id=getattr(model, "tenant_id", tenant_id()),
        bpmn_model_id=model.id,
        process_id=model.process_id,
        xml=xml,
        change_summary=change_summary.strip() or "Aggiornamento BPMN",
        source=source.strip() or "manual",
        created_at=now_iso(),
    )
    session.add(version)
    return version


def update_bpmn_model(
    bpmn_model_id: str,
    xml: str,
    change_summary: str = "Salvataggio canvas",
    source: str = "manual_save",
    expected_version_id: int | None | _NoPrecondition = NO_PRECONDITION,
) -> dict | None:
    """
    Persist an authorized BPMN model update and create a version snapshot.
    
    Args:
        bpmn_model_id (str): Tenant-scoped model identifier.
        xml (str): Untrusted BPMN XML content; it must contain non-whitespace
            characters.
        change_summary (str): Untrusted description of the change.
        source (str): Untrusted origin label for the version snapshot.
        expected_version_id (int | None): Untrusted id of the version the
            writer started from; `None` means the model had no version yet.
            When given, the save is refused if the latest version differs.
            Omitted (`NO_PRECONDITION`) for internal callers.
    
    Returns:
        dict | None: The updated model data, or `None` when the model does not
        belong to the current tenant or does not exist.
    
    Raises:
        PermissionError: If the caller is not authorized to write BPMN models.
        ValueError: If `xml` is empty or contains only whitespace.
        BpmnVersionConflict: If someone else saved a version the writer has
            not seen (see `_assert_bpmn_not_changed_underneath`).
    
    Side Effects:
        Updates the tenant-owned BPMN model and persists a version snapshot.
    """
    assert_write_allowed("update_bpmn_model")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        clean_xml = xml.strip()
        if not clean_xml:
            raise ValueError("XML BPMN obbligatorio.")

        # Blocca la riga del modello fino al commit: due salvataggi concorrenti
        # si mettono in fila, e il secondo vede la versione scritta dal primo.
        session.refresh(model, with_for_update=True)
        _assert_bpmn_not_changed_underneath(session, model.id, expected_version_id)

        model.xml = clean_xml
        # Il disegno e' cambiato: il confronto con le fonti che risultava prima
        # non descrive piu' cio' che si vede. Va rifatto, e lo fa il worker.
        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") == tenant_id():
            _queue_conformance(review)
        version = create_bpmn_version(
            session=session,
            model=model,
            xml=clean_xml,
            change_summary=change_summary,
            source=source,
        )
        session.flush()
        _remember_turn_write(model.id, version.id)
        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
            "version_id": version.id,
        }


def list_bpmn_versions(bpmn_model_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceBpmnModel, bpmn_model_id) is None:
            return []

        statement = (
            select(WorkspaceBpmnVersion)
            .where(WorkspaceBpmnVersion.bpmn_model_id == bpmn_model_id)
            .where(WorkspaceBpmnVersion.tenant_id == tenant_id())
            .order_by(WorkspaceBpmnVersion.id.desc())
        )
        versions = session.execute(statement).scalars().all()
        return [bpmn_version_to_dict(version) for version in versions]


def restore_bpmn_version(bpmn_model_id: str, version_id: int) -> dict:
    """Restore a tenant-owned BPMN model to a prior version and record the restoration.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        version_id (int): Untrusted version identifier to restore.
    
    Returns:
        dict: The restored BPMN model, the source version, and the newly created
            restoration version.
    
    Raises:
        ValueError: If the model or version does not exist, or the version does
            not belong to the specified model and current tenant.
        PermissionError: If the caller is not authorized to modify BPMN data.
    
    Side Effects:
        Persists the restored XML and creates a new BPMN version recording the
        restoration.
    """
    assert_write_allowed("restore_bpmn_version")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        version = session.get(WorkspaceBpmnVersion, version_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if (
            version is None
            or version.bpmn_model_id != bpmn_model_id
            or getattr(version, "tenant_id", "local") != tenant_id()
        ):
            raise ValueError(f"Versione BPMN non trovata: {version_id}")

        # Come ogni scrittura del disegno: in fila dietro le altre, e mai sopra
        # una versione che chi ripristina (dentro un turno) non ha visto.
        session.refresh(model, with_for_update=True)
        _assert_bpmn_not_changed_underneath(session, model.id, NO_PRECONDITION)
        model.xml = version.xml
        restored = create_bpmn_version(
            session=session,
            model=model,
            xml=version.xml,
            change_summary=f"Ripristino versione {version_id}",
            source="restore",
        )
        session.flush()
        _remember_turn_write(model.id, restored.id)
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
                "version_id": restored.id,
            },
            "restored_from": bpmn_version_to_dict(version),
            "created_version": bpmn_version_to_dict(restored),
        }


def _open_missing_information(review) -> list[str]:
    """Filter unresolved review information to exclude questions already answered.
    
    Args:
        review (object): Untrusted review record containing stored missing-information
            and answer data.
    
    Returns:
        list[str]: Missing-information items whose question identifiers have not been
        answered.
    
    The function does not modify or persist the review.
    """
    answered = {
        unknown_question_id(item.get("question") or "")
        for item in decode_answers(review)
    }
    return [
        item
        for item in decode_list(review.missing_information_json)
        if unknown_question_id(item) not in answered
    ]


def decode_answers(review) -> list[dict]:
    """Decode a review's stored answers into a list.
    
    Args:
        review: An object whose ``answers_json`` attribute contains JSON data.
            The stored value is treated as untrusted input.
    
    Returns:
        The decoded list of answer dictionaries, or an empty list when the
        attribute is missing, empty, or contains a JSON value of another type.
    
    Raises:
        json.JSONDecodeError: If ``answers_json`` contains malformed JSON.
    """
    parsed = json.loads(getattr(review, "answers_json", "[]") or "[]")
    return parsed if isinstance(parsed, list) else []


def answered_unknowns(review) -> list[ProcessUnknown]:
    """Le domande a cui il consulente ha risposto, da riportare nel piano nuovo.

    La domanda si prende dal piano corrente quando c'e' - con il suo contesto,
    le alternative, la gravita' - e altrimenti si ricostruisce dal testo salvato
    insieme alla risposta: una risposta data a una versione di tre ricostruzioni
    fa resta comunque la risposta di chi conosce il processo (L9).

    Args:
        review: La review corrente, o ``None`` per un piano che nasce adesso.

    Returns:
        Le domande risposte, nell'ordine in cui sono state risposte.

    Sola lettura.
    """
    if review is None:
        return []
    answers = decode_answers(review)
    if not answers:
        return []
    semantic_model = json.loads(getattr(review, "bpmn_semantic_model_json", None) or "{}")
    understanding = semantic_model.get("sourceProcessUnderstanding") or {}
    current = {
        unknown_question_id(str(item.get("question") or "")): item
        for item in understanding.get("unknowns") or []
        if isinstance(item, dict) and item.get("question")
    }
    carried: list[ProcessUnknown] = []
    for answer in answers:
        question = " ".join(str(answer.get("question") or "").split())
        question_id = str(answer.get("question_id") or unknown_question_id(question))
        raw = current.get(question_id) or ({"question": question, "affects": ""} if question else None)
        if raw is None:
            continue
        try:
            carried.append(ProcessUnknown.model_validate(raw))
        except ValueError:
            logger.warning("domanda risposta non riportabile nel piano: %s", question_id, exc_info=True)
    return carried


def unanswered_questions(review) -> list[dict]:
    """Identify review questions that still require an answer.
    
    Args:
        review: Untrusted review data from which to derive open questions.
    
    Returns:
        A list of question dictionaries whose answers are empty or absent.
    """
    return [item for item in open_questions_with_answers(review) if not item.get("answer")]


def open_questions_with_answers(review) -> list[dict]:
    """
    Builds actionable review questions from the stored process understanding and recorded answers.
    
    Args:
        review: [Untrusted] Review record containing the serialized semantic model and answers.
    
    Returns:
        A list of question dictionaries with stable IDs, alternatives, severity,
        impact, and any recorded answer metadata.
    
    Raises:
        json.JSONDecodeError: If the stored semantic model is not valid JSON.
    
    This function does not modify or persist data.
    """
    semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    understanding = semantic_model.get("sourceProcessUnderstanding") or {}
    answers = {item.get("question_id"): item for item in decode_answers(review)}

    questions = []
    for unknown in understanding.get("unknowns") or []:
        if not isinstance(unknown, dict):
            continue
        question = str(unknown.get("question") or "").strip()
        if not question:
            continue
        question_id = unknown_question_id(question)
        questions.append(
            {
                "question_id": question_id,
                "question": question,
                "affects": unknown.get("affects") or "",
                "severity": unknown.get("severity") or "non_blocking",
                # Da dove nasce la domanda: quale voce ha detto cosa, e cosa
                # resta scoperto. Senza questo al consulente arriva "chi
                # approva?" - una domanda da questionario, indistinguibile da
                # quella che si farebbe prima di aver sentito qualcuno.
                "grounded_in": str(unknown.get("grounded_in") or ""),
                "options": [
                    {
                        "label": str(option.get("label") or ""),
                        "implication": str(option.get("implication") or ""),
                    }
                    for option in unknown.get("options") or []
                    if isinstance(option, dict) and option.get("label")
                ],
                "answer": answers.get(question_id, {}).get("answer"),
                "answered_at": answers.get(question_id, {}).get("answered_at"),
            }
        )
    return questions


def answer_bpmn_review_question(
    bpmn_model_id: str,
    question: str,
    answer: str,
) -> dict:
    """Record or replace an answer to a BPMN review question and persist a review-version snapshot.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        question (str): Untrusted question text; must contain non-whitespace content.
        answer (str): Untrusted answer text; must contain non-whitespace content.
    
    Returns:
        dict: The updated BPMN review, including the recorded answer and incremented version.
    
    Raises:
        ValueError: If the question or answer is empty, or if no tenant-owned review
            exists for the specified BPMN model.
    
    The answer is stored for later review revision and does not modify the process model.
    """
    assert_write_allowed("answer_bpmn_review_question")
    clean_question = " ".join(str(question or "").split())
    clean_answer = str(answer or "").strip()
    if not clean_question:
        raise ValueError("Domanda obbligatoria.")
    if not clean_answer:
        raise ValueError("La risposta non può essere vuota.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError("Nessuna review BPMN da aggiornare per questo canvas.")

        question_id = unknown_question_id(clean_question)
        recorded = [
            item
            for item in decode_answers(review)
            if item.get("question_id") != question_id
        ]
        recorded.append(
            {
                "question_id": question_id,
                "question": clean_question,
                "answer": clean_answer,
                "answered_at": now_iso(),
            }
        )

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.answers_json = json.dumps(recorded, ensure_ascii=False)
        review.updated_at = now_iso()
        _record_review_version(
            session,
            review,
            change_summary=f"Risposta a: {clean_question}",
            source="answer",
        )
        session.flush()
        return review_to_dict(review)


class UnreadableReviewError(ValueError):
    """La review salvata non e' leggibile, e riprovare non la rendera' tale.

    Un semantic model legacy o un ProcessUnderstanding placeholder da estrazione
    fallita restano quello che sono finche' qualcuno non rigenera il piano:
    nessun tentativo successivo cambia l'esito. Il tipo serve a chi lavora una
    coda, che altrimenti non puo' distinguere questo da una chiamata al modello
    andata storta - e rimette in coda per sempre una riga che fallira' sempre.
    """


def _review_artifacts(review) -> tuple[dict, dict]:
    """Validate and derive artifacts from a stored BPMN review.

    Args:
        review: Untrusted stored review row containing serialized semantic-model data.

    Returns:
        A tuple containing the canonical semantic model and its recomputed quality
        report.

    Raises:
        UnreadableReviewError: If the stored semantic model is not canonical, or if
            the stored process understanding cannot be validated or has no
            applicable quality report (extraction-failure placeholder). Sempre
            permanente: la review va rigenerata, non riletta.
        json.JSONDecodeError: If the stored payload cannot be decoded.

    The function does not persist changes or otherwise modify the review.
    """
    bpmn_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    if not _is_canonical_semantic_model_payload(bpmn_semantic_model):
        raise UnreadableReviewError("Review BPMN legacy rifiutata: semantic model non canonicale.")
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    try:
        quality_report = quality_report_from_understanding(
            ProcessUnderstanding.model_validate(process_understanding)
        ).model_dump(mode="json")
    except ValueError as exc:
        # `ValidationError` di pydantic e' un `ValueError`: struttura non valida e
        # placeholder da estrazione fallita finiscono nello stesso stato, ed e'
        # lo stesso stato - questa review non si puo' leggere cosi' com'e'.
        raise UnreadableReviewError(
            f"Review BPMN non leggibile per {getattr(review, 'bpmn_model_id', '?')}: {exc}"
        ) from exc
    return bpmn_semantic_model, quality_report


def review_version_to_dict(version: WorkspaceBpmnReviewVersion) -> dict:
    """
    Serialize a BPMN review version with its semantic model, quality report, questions, answers, and metadata.
    
    Args:
        version (WorkspaceBpmnReviewVersion): Review version to serialize.
    
    Returns:
        dict: Serialized review version data, including open questions and decoded answers.
    
    Raises:
        ValueError: If the stored review artifacts are invalid.
    
    The function does not modify or persist the review version.
    """
    bpmn_semantic_model, quality_report = _review_artifacts(version)
    return {
        "bpmn_model_id": version.bpmn_model_id,
        "process_id": version.process_id,
        "version": version.version,
        "status": version.status,
        "change_summary": version.change_summary,
        "source": version.source,
        "source_text": version.source_text,
        "process_understanding": bpmn_semantic_model.get("sourceProcessUnderstanding") or {},
        "bpmn_semantic_model": bpmn_semantic_model,
        "quality_report": quality_report,
        "bpmn_brief": version.bpmn_brief,
        "readiness_score": version.readiness_score,
        "missing_information": _open_missing_information(version),
        # La provenance viaggia anche nella storia: "questa versione del piano su
        # quali fonti era costruita" e' la domanda che rende leggibile un
        # confronto fra due versioni, e la colonna la salvava gia' senza che
        # nessuno potesse rileggerla.
        "evidence_source_set_id": getattr(version, "evidence_source_set_id", None),
        "open_questions": open_questions_with_answers(version),
        "answers": decode_answers(version),
        "created_at": version.created_at,
    }


def _record_review_version(
    session,
    review: WorkspaceBpmnReview,
    *,
    change_summary: str,
    source: str,
) -> WorkspaceBpmnReviewVersion:
    """Create a persistent snapshot of the review at its current version.
    
    Args:
        change_summary (str): Untrusted description of the change represented by
            the snapshot.
        source (str): Untrusted identifier for the snapshot's origin.
    
    Returns:
        WorkspaceBpmnReviewVersion: The newly created, unsaved snapshot object.
    
    Side effects:
        Adds the snapshot to the provided database session.
    """
    version = WorkspaceBpmnReviewVersion(
        tenant_id=getattr(review, "tenant_id", tenant_id()),
        bpmn_model_id=review.bpmn_model_id,
        process_id=review.process_id,
        version=review.version,
        source_text=review.source_text,
        process_understanding_json=review.process_understanding_json,
        bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        bpmn_brief=review.bpmn_brief,
        readiness_score=review.readiness_score,
        missing_information_json=review.missing_information_json,
        evidence_source_set_id=getattr(review, "evidence_source_set_id", None),
        answers_json=getattr(review, "answers_json", "[]") or "[]",
        status=review.status,
        change_summary=change_summary,
        source=source,
        created_at=now_iso(),
    )
    session.add(version)
    return version


def _mark_review_version_approved(session, review: WorkspaceBpmnReview) -> None:
    """Mark the current review version as approved in the review history.
    
    If no matching historical snapshot exists, records one before marking approval.
    Persists the approval status and summary through the supplied database session.
    
    Args:
        session: Database session used to update or create the review version.
        review: Review whose tenant, BPMN model, and version identify the snapshot.
    
    """
    row = (
        session.execute(
            select(WorkspaceBpmnReviewVersion).where(
                WorkspaceBpmnReviewVersion.bpmn_model_id == review.bpmn_model_id,
                WorkspaceBpmnReviewVersion.version == review.version,
                WorkspaceBpmnReviewVersion.tenant_id == getattr(review, "tenant_id", tenant_id()),
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        # A review stored before versioning existed has no snapshot to mark; record
        # one now so its approval is not the only state missing from the history.
        _record_review_version(
            session,
            review,
            change_summary="Piano approvato: canvas generato",
            source="approval",
        )
        return

    row.status = "approved"
    row.change_summary = "Piano approvato: canvas generato"


def list_bpmn_review_versions(bpmn_model_id: str) -> list[dict]:
    """List tenant-scoped review snapshots for a BPMN model, newest first.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier used to select review
            snapshots within the current tenant.
    
    Returns:
        list[dict]: Review snapshots ordered from newest to oldest. Returns an
            empty list when no snapshots match.
    """
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspaceBpmnReviewVersion)
                .where(
                    WorkspaceBpmnReviewVersion.bpmn_model_id == bpmn_model_id,
                    WorkspaceBpmnReviewVersion.tenant_id == tenant_id(),
                )
                .order_by(WorkspaceBpmnReviewVersion.version.desc())
            )
            .scalars()
            .all()
        )
        return [review_version_to_dict(row) for row in rows]


def get_bpmn_review_version(bpmn_model_id: str, version: int) -> dict | None:
    """Retrieve a tenant-scoped BPMN review version.
    
    Args:
        bpmn_model_id: Untrusted BPMN model identifier.
        version: Untrusted review version number.
    
    Returns:
        A serialized review version for the current tenant, or `None` if no matching
        version exists.
    """
    with workspace_connection() as session:
        row = (
            session.execute(
                select(WorkspaceBpmnReviewVersion).where(
                    WorkspaceBpmnReviewVersion.bpmn_model_id == bpmn_model_id,
                    WorkspaceBpmnReviewVersion.version == version,
                    WorkspaceBpmnReviewVersion.tenant_id == tenant_id(),
                )
            )
            .scalars()
            .first()
        )
        return review_version_to_dict(row) if row else None


def review_to_dict(review: WorkspaceBpmnReview) -> dict:
    """Serialize a BPMN review and its derived artifacts for API responses.
    
    Args:
        review (WorkspaceBpmnReview): Review record to serialize.
    
    Returns:
        dict: Review data including semantic model, quality report, readiness,
            missing information, questions, answers, status, and timestamps.
    
    This function does not modify or persist the review.
    """
    bpmn_semantic_model, quality_report = _review_artifacts(review)
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    return {
        "bpmn_model_id": review.bpmn_model_id,
        "process_id": review.process_id,
        "version": getattr(review, "version", 1),
        "source_text": review.source_text,
        "process_understanding": process_understanding,
        "bpmn_semantic_model": bpmn_semantic_model,
        "quality_report": quality_report,
        "bpmn_brief": review.bpmn_brief,
        "readiness_score": review.readiness_score,
        "missing_information": _open_missing_information(review),
        # Su quali fonti questo piano e' nato. Chi legge puo' confrontarlo con il
        # registro dell'evidenza di adesso e sapere se il piano e' indietro.
        "evidence_source_set_id": getattr(review, "evidence_source_set_id", None),
        "open_questions": open_questions_with_answers(review),
        "answers": decode_answers(review),
        "element_decisions": decode_element_decisions(review),
        "conformance": conformance_state(review),
        "status": getattr(review, "status", "pending"),
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def get_bpmn_review(bpmn_model_id: str, include_approved: bool = False) -> dict | None:
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)

        if review is None:
            return None
        if not include_approved and getattr(review, "status", "pending") != "pending":
            return None
        stored_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
        if not _is_canonical_semantic_model_payload(stored_semantic_model):
            return None

        return review_to_dict(review)


def update_bpmn_review_brief(bpmn_model_id: str, bpmn_brief: str) -> dict:
    """Update the reader-facing narrative of a pending BPMN review.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier used to locate the
            tenant-owned review.
        bpmn_brief (str): Untrusted Markdown brief. It is trimmed and must contain
            non-whitespace content.
    
    Returns:
        dict: The updated serialized BPMN review.
    
    Raises:
        ValueError: If the brief is empty, or if no pending tenant-owned review
            exists for the specified model.
    
    Side Effects:
        Persists the trimmed brief, increments the review version, updates its
        timestamp, and records a new review-version snapshot. The semantic model
        and canvas-generation content remain unchanged.
    """
    assert_write_allowed("update_bpmn_review_brief")
    clean_brief = bpmn_brief.strip()
    if not clean_brief:
        raise ValueError("Il piano Markdown non può essere vuoto.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None or getattr(review, "status", "pending") != "pending":
            raise ValueError("Nessuna review BPMN pendente da salvare.")

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.bpmn_brief = clean_brief
        review.updated_at = now_iso()
        _record_review_version(
            session,
            review,
            change_summary="Testo del piano modificato",
            source="brief_edit",
        )
        session.flush()
        return review_to_dict(review)


def _is_canonical_semantic_model_payload(value: dict) -> bool:
    return bool(
        value.get("flowNodes")
        and value.get("sequenceFlows")
        and value.get("compilationPlan")
        and value.get("sourceProcessUnderstanding")
    )


# "Non e' stato detto" e "e' stato detto: nessuna fonte" sono due cose diverse, e
# `None` non poteva esprimerle entrambe. I chiamanti che non conoscono il set di
# fonti - i tool che ricostruiscono la review da prosa - passavano implicitamente
# `None` e cancellavano la provenance di un piano nato dalle interviste: da quel
# momento il piano risultava "di provenienza ignota" e veniva risintetizzato a
# ogni giro.
class _KeepExistingValue:
    """L'argomento non e' stato passato, che non e' "passato vuoto"."""

    __slots__ = ()


_KEEP_EVIDENCE_SOURCE_SET = _KeepExistingValue()


def prepare_bpmn_review(
    bpmn_model_id: str,
    process_description: str,
    process_understanding: dict | None = None,
    evidence_source_set_id: str | None | _KeepExistingValue = _KEEP_EVIDENCE_SOURCE_SET,
) -> dict:
    """Prepare and persist a pending BPMN review for a model.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier. The model must belong to
            the current tenant.
        process_description (str): Untrusted process description. It must contain
            non-whitespace text.
        process_understanding (dict | None): Untrusted optional process understanding
            used to generate the review draft.
        evidence_source_set_id (str | None): Identity of the evidence source set this
            plan was built on. Recorded so a later turn can tell an up-to-date plan
            from one that predates a source. Omit it to keep whatever the existing
            review declares: a caller that does not know the source set must not
            erase the provenance of a plan that was built on the interviews.

    Returns:
        dict: The serialized, pending BPMN review.
    
    Raises:
        ValueError: If the process description is empty or the BPMN model cannot be
            found for the current tenant.
    
    The review is persisted in the workspace. A new review starts at version 1;
    preparing an existing review creates its next version while preserving the
    previous snapshot.
    """
    assert_write_allowed("prepare_bpmn_review")
    clean_text = process_description.strip()
    if not clean_text:
        raise ValueError("Descrizione processo obbligatoria.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") != current_tenant_id:
            review = None

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=clean_text,
            process_understanding=process_understanding,
            # Una ricostruzione del piano riparte dalle fonti, ma le risposte del
            # consulente non vengono dalle fonti: si riportano, non si
            # rigenerano (L9). E' qui e non in chi chiama perche' questo e'
            # l'unico punto da cui passa ogni ricostruzione, presente e futura.
            answered_questions=answered_unknowns(review),
        )

        timestamp = now_iso()

        if review is None:
            review = WorkspaceBpmnReview(
                tenant_id=current_tenant_id,
                bpmn_model_id=bpmn_model_id,
                process_id=model.process_id,
                version=1,
                source_text=review_draft.source_text,
                process_understanding_json=review_draft.process_understanding_json(),
                bpmn_semantic_model_json=review_draft.bpmn_semantic_model_json(),
                bpmn_brief=review_draft.bpmn_brief,
                readiness_score=review_draft.readiness_score,
                missing_information_json=encode_list(review_draft.missing_information),
                evidence_source_set_id=(
                    None
                    if isinstance(evidence_source_set_id, _KeepExistingValue)
                    else evidence_source_set_id
                ),
                status="pending",
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(review)
        else:
            # A new preparation does not erase the previous plan: it becomes the
            # next version, and what it replaced stays readable and comparable.
            review.version = int(getattr(review, "version", 1) or 1) + 1
            review.source_text = review_draft.source_text
            review.process_understanding_json = review_draft.process_understanding_json()
            review.bpmn_semantic_model_json = review_draft.bpmn_semantic_model_json()
            review.bpmn_brief = review_draft.bpmn_brief
            review.readiness_score = review_draft.readiness_score
            review.missing_information_json = encode_list(review_draft.missing_information)
            if not isinstance(evidence_source_set_id, _KeepExistingValue):
                review.evidence_source_set_id = evidence_source_set_id
            review.status = "pending"
            review.updated_at = timestamp

        # Il piano e' cambiato: il confronto con le fonti che risultava prima
        # descrive un altro piano. Va rifatto, e lo fa il worker.
        _queue_conformance(review)
        _record_review_version(
            session,
            review,
            change_summary="Piano preparato dalla descrizione del processo",
            source="prepare",
        )
        session.flush()
        return review_to_dict(review)


def revise_bpmn_review(
    bpmn_model_id: str,
    process_understanding: dict,
    change_summary: str = "",
) -> dict:
    """Rebuild a pending BPMN review from corrected process understanding.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier scoped to the current tenant.
        process_understanding (dict): Untrusted corrected process understanding used to
            regenerate the review artifacts.
        change_summary (str): Untrusted description recorded with the revision snapshot.
    
    Raises:
        ValueError: If the BPMN model is not found for the current tenant or no review
            exists for the model.
    
    Returns:
        dict: The revised review, including its regenerated brief, semantic model,
            readiness data, missing information, status, and version.
    
    The revision persists the updated review, records a historical version, increments
    the review version, and reopens the review with pending status.
    """
    assert_write_allowed("revise_bpmn_review")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError("Nessuna review BPMN da rivedere per questo canvas.")

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=review.source_text,
            process_understanding=process_understanding,
            answered_questions=answered_unknowns(review),
        )

        review.version = int(getattr(review, "version", 1) or 1) + 1
        review.process_understanding_json = review_draft.process_understanding_json()
        review.bpmn_semantic_model_json = review_draft.bpmn_semantic_model_json()
        review.bpmn_brief = review_draft.bpmn_brief
        review.readiness_score = review_draft.readiness_score
        review.missing_information_json = encode_list(review_draft.missing_information)
        # A revision reopens the plan: an approved review that gets corrected is a
        # new proposal, not a still-approved one.
        review.status = "pending"
        # E il confronto con le fonti descriveva il piano di prima: va rifatto.
        _queue_conformance(review)
        review.updated_at = now_iso()

        _record_review_version(
            session,
            review,
            change_summary=change_summary.strip() or "Piano rivisto dal consulente",
            source="revision",
        )
        session.flush()
        return review_to_dict(review)


def approve_bpmn_review(bpmn_model_id: str, *, override: bool = False) -> dict:
    """
    Approve a BPMN review and persist the generated BPMN model.
    
    Args:
        bpmn_model_id (str): Untrusted identifier of the tenant-scoped BPMN model.
        override (bool): Whether to bypass review-readiness checks.
    
    Returns:
        dict: A payload containing the approved BPMN model and review data.
    
    Raises:
        ValueError: If the BPMN model or review does not exist, or the review is
            not ready for approval.
        PermissionError: If the caller is not authorized to perform writes.
    
    The function persists the generated BPMN XML, records a BPMN version linked to
    the approved review version, and marks the review as approved.
    """
    assert_write_allowed("approve_bpmn_review")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if review is None:
            raise ValueError("Nessuna review BPMN pronta da approvare per questo canvas.")

        if not override:
            _assert_review_ready_for_approval(review)

        xml, _layout_report = optimize_bpmn_layout(bpmn_xml_from_review(
            bpmn_semantic_model_json=review.bpmn_semantic_model_json,
        ))
        model.xml = xml
        approved_version = int(getattr(review, "version", 1) or 1)
        create_bpmn_version(
            session=session,
            model=model,
            xml=xml,
            # Which plan produced this drawing, so a canvas version can be traced
            # back to the review it came from.
            change_summary=f"Generazione da review BPMN approvata (v{approved_version})",
            source="review_approval",
        )
        review.status = "approved"
        review.updated_at = now_iso()
        # Approving does not change what the plan says, only its standing, so the
        # recorded version is marked rather than duplicated.
        _mark_review_version_approved(session, review)
        review_payload = review_to_dict(review)
        session.flush()
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
            },
            "review": review_payload,
        }


# Il valutatore chiede all'utente di chiarire; una volta che l'utente ha
# chiarito, l'attesa non ha piu' oggetto. Le altre raccomandazioni riguardano il
# modello, non l'utente, e continuano a bloccare.
_RECOMMENDATION_WAITING_ON_THE_USER = "needs_user_clarification"


def review_approval_blockers(
    quality_report: dict | None,
    semantic_model: dict | None,
    *,
    open_questions_pending: bool = True,
) -> list[str]:
    """Identifies reasons a BPMN review cannot be automatically approved.
    
    Args:
        quality_report (dict | None): Untrusted quality-evaluation data. A
            recommendation other than ``"ready_to_generate"`` is a blocker, except
            ``"needs_user_clarification"`` when ``open_questions_pending`` is
            ``False``.
        semantic_model (dict | None): Untrusted semantic-model data checked for
            control-flow soundness.
        open_questions_pending (bool): Whether unanswered review questions remain.
    
    Returns:
        list[str]: Approval-blocker descriptions. Invalid semantic-model data
        contributes no control-flow blockers.
    
    The function performs no persistence or other side effects.
    """
    from backend.bpmn import BPMNSemanticModel
    from backend.bpmn.soundness import analyze_control_flow

    blockers: list[str] = []
    recommendation = (quality_report or {}).get("approval_recommendation")
    waiting_on_answered_questions = (
        recommendation == _RECOMMENDATION_WAITING_ON_THE_USER and not open_questions_pending
    )
    if recommendation and recommendation != "ready_to_generate" and not waiting_on_answered_questions:
        blockers.append(f"la valutazione qualita' e' '{recommendation}', non 'ready_to_generate'.")

    try:
        model = BPMNSemanticModel.model_validate(semantic_model or {})
    except Exception:
        return blockers
    for issue in analyze_control_flow(model).errors:
        blockers.append(f"control-flow: {issue.message}")
    return blockers


def _assert_review_ready_for_approval(review: WorkspaceBpmnReview) -> None:
    """Validate that a BPMN review satisfies all approval requirements.
    
    Args:
        review (WorkspaceBpmnReview): Review to validate.
    
    Raises:
        ValueError: If the review has one or more approval blockers.
    
    The function does not modify or persist the review.
    """
    payload = review_to_dict(review)
    blockers = review_approval_blockers(
        payload.get("quality_report"),
        payload.get("bpmn_semantic_model"),
        open_questions_pending=bool(unanswered_questions(review)),
    )
    if blockers:
        raise ValueError(
            "Review non approvabile: "
            + "; ".join(blockers[:5])
            + ". Correggere il processo oppure approvare con override."
        )


def source_to_dict(source: WorkspaceSource) -> dict:
    def structured(raw: str | None) -> list:
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    return {
        "id": source.id,
        "project_id": source.project_id,
        "client_id": source.client_id,
        "process_id": source.process_id,
        "name": source.name,
        "type": source.type,
        "meta": source.meta,
        "roles": structured(source.roles_json),
        "retention": source.retention,
        "scopes": structured(source.scopes_json),
        "status": source.status,
        # Stringa vuota e non `None`: chi legge confronta impronte, e un `None`
        # fra due confronti si comporta in modo diverso da un testo assente.
        "content_hash": getattr(source, "content_hash", None) or "",
        "byte_size": source.byte_size,
        "mime_type": source.mime_type,
        "acquisition_status": source.acquisition_status,
        "acquisition_error": source.acquisition_error,
        "claims_status": source.claims_status,
        "claims_error": source.claims_error,
        "reconcile_status": source.reconcile_status,
    }


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
            owner_client_id = tenant_row(session, WorkspaceProject, project_id).client_id
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


def _claims_as_input(session, sources: list[WorkspaceSource]) -> list[dict]:
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
        others = (
            select(WorkspaceSource)
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
            _claims_as_input(session, list(session.execute(others).scalars().all())),
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


ELEMENT_DECISIONS = frozenset({"confirmed", "rejected"})


class _ElementDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: Literal["confirmed", "rejected"]
    label: str = ""
    note: str = ""
    decided_at: str = ""
    plan_version: int = 0


def decode_element_decisions(review: WorkspaceBpmnReview) -> dict[str, dict]:
    """Le decisioni del consulente sugli elementi del piano, per riferimento.

    Ogni voce si valida da sola. Una voce rovinata si scarta e si scrive nei log;
    un intero documento illeggibile si scarta allo stesso modo. Non si solleva:
    una colonna rovinata renderebbe illeggibile l'intero processo, e il danno di
    perdere una conferma e' molto piu' piccolo - si riconferma, e il segno sul
    disegno torna "da confermare", che e' la parte prudente dell'errore.
    """
    raw = getattr(review, "element_decisions_json", None) or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "decisioni sugli elementi illeggibili per il modello %s: scartate",
            getattr(review, "bpmn_model_id", "?"),
        )
        return {}
    if not isinstance(parsed, dict):
        logger.warning(
            "decisioni sugli elementi non in forma di mappa per il modello %s: scartate",
            getattr(review, "bpmn_model_id", "?"),
        )
        return {}
    decisions: dict[str, dict] = {}
    for source_ref, value in parsed.items():
        try:
            decisions[str(source_ref)] = _ElementDecisionRecord.model_validate(value).model_dump()
        except ValidationError:
            logger.warning(
                "decisione non valida su %s per il modello %s: scartata",
                source_ref,
                getattr(review, "bpmn_model_id", "?"),
            )
    return decisions


def record_element_decision(
    bpmn_model_id: str,
    *,
    source_ref: str,
    label: str,
    decision: str,
    note: str = "",
) -> dict[str, dict]:
    """Registra che il consulente ha confermato o rifiutato un elemento del piano.

    Non passa da `assert_write_allowed`: e' una revisione umana fatta dal
    pannello delle evidenze, fuori da qualunque turno di chat, come l'approvazione
    di una review.

    Args:
        bpmn_model_id: Il modello a cui la review appartiene.
        source_ref: Il riferimento di tracciabilita' dell'elemento.
        label: L'etichetta dell'elemento al momento della decisione. Si tiene
            perche' un piano ricostruito puo' riusare lo stesso id per un
            passaggio diverso, e chi rilegge la decisione deve poterlo vedere.
        decision: `confirmed` o `rejected`.
        note: Perche', se il consulente lo scrive.

    Returns:
        Tutte le decisioni della review, dopo la scrittura.

    Raises:
        ValueError: Se la decisione non e' ammessa o la review non esiste.
    """
    if decision not in ELEMENT_DECISIONS:
        raise ValueError(f"Decisione non ammessa: {decision}")
    if not str(source_ref or "").strip():
        raise ValueError("Riferimento dell'elemento obbligatorio.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError(f"Review BPMN non trovata: {bpmn_model_id}")
        decisions = decode_element_decisions(review)
        decisions[source_ref] = {
            "decision": decision,
            "label": label,
            "note": note.strip(),
            "decided_at": now_iso(),
            "plan_version": int(getattr(review, "version", 1) or 1),
        }
        review.element_decisions_json = json.dumps(decisions, ensure_ascii=False)
        review.updated_at = now_iso()
        session.flush()
        return decisions


def conformance_state(review: WorkspaceBpmnReview) -> dict:
    """Lo stato del confronto disegno-piano-fonti di questa review.

    `status` dice se un confronto e' in attesa di girare; `report` e' l'ultimo
    esito, che resta leggibile anche mentre il prossimo e' in coda: il consulente
    continua a vedere cosa risultava, con l'avviso che le cose sono cambiate.
    """
    return {
        "status": getattr(review, "conformance_status", None) or "none",
        "report": decode_conformance_report(review),
    }


def decode_conformance_report(review: WorkspaceBpmnReview) -> dict | None:
    """L'ultima verifica di conformita' registrata, se leggibile.

    Un rapporto illeggibile vale come nessun rapporto: chi lo legge deve rifare
    la verifica, non fidarsi di un dato rovinato.
    """
    raw = getattr(review, "conformance_json", None)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "rapporto di conformita' illeggibile per il modello %s: ignorato",
            getattr(review, "bpmn_model_id", "?"),
        )
        return None
    return parsed if isinstance(parsed, dict) else None


def record_conformance_report(bpmn_model_id: str, report: dict) -> dict | None:
    """Registra sulla review l'esito dell'ultima verifica disegno-piano-fonti.

    Non alza la versione del piano e non passa da `assert_write_allowed`: e' la
    registrazione di un controllo, come la coda di materializzazione, non una
    modifica del processo. Il rapporto porta lo snapshot e l'impronta del canvas
    su cui e' stato fatto, quindi chi lo rilegge sa se vale ancora.

    Returns:
        Il rapporto registrato, o ``None`` se la review non esiste nel tenant.
    """
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            return None
        review.conformance_json = json.dumps(report, ensure_ascii=False)
        review.conformance_status = "done"
        review.conformance_leased_at = None
        session.flush()
        return report


def request_conformance_check(bpmn_model_id: str) -> bool:
    """Segna che il confronto con le fonti va rifatto.

    Lo scrivono le operazioni che cambiano cio' che il confronto guarda: una
    bozza appena disegnata, un canvas salvato, un piano rivisto. Il disegno esce
    subito e la verifica gira dietro - il consulente itera invece di aspettare -
    e finche' non e' finita il pannello dice che e' in corso.

    Non alza la versione del piano e non passa da `assert_write_allowed`: e' la
    registrazione di un lavoro da fare, come la coda di materializzazione.

    Returns:
        `True` se la richiesta e' stata registrata; `False` se il processo non ha
        una review (niente piano, niente da confrontare).
    """
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            return False
        _queue_conformance(review)
        session.flush()
        return True


def _queue_conformance(review: WorkspaceBpmnReview) -> None:
    """Rimette in coda il confronto di un disegno nuovo, con i tentativi a zero.

    I tentativi contano i fallimenti dello stesso disegno: quando il disegno o
    il piano cambiano, il confronto e' un altro e riparte da capo.
    """
    review.conformance_status = "pending"
    review.conformance_attempts = 0


def due_conformance_checks(limit: int = 3, *, only_tenant_id: str | None = None) -> list[dict]:
    """I confronti in attesa, i piu' vecchi per primi, presi in carico con una scadenza.

    Come la coda dei piani: il worker gira fuori da una richiesta HTTP, quindi la
    riga porta il proprio tenant, e chi la prende in carico lo vincola prima di
    leggere il processo. La presa in carico marca `running` **e quando**: una
    lettura delle fonti dura minuti, e se il processo che la stava facendo muore -
    un riavvio, un deploy - la riga deve tornare eleggibile da sola. Senza la
    scadenza resta `running` per sempre, nessuno la rilavora, e il pannello mostra
    "Confronto in corso" all'infinito: sembra lavoro in corso e non lo e'.

    Args:
        limit: Quante righe prendere in carico.
        only_tenant_id: Limita la coda a un tenant. I test drenano cosi', perche'
            una passata che prende la riga di un altro workspace scriverebbe un
            rapporto dentro il processo di un cliente.

    Side effects:
        Marca le righe prese in carico e ne segna l'istante.
    """
    expired_before = (
        datetime.now(UTC) - timedelta(seconds=CONFORMANCE_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceBpmnReview)
            .where(
                or_(
                    WorkspaceBpmnReview.conformance_status == "pending",
                    and_(
                        WorkspaceBpmnReview.conformance_status == "running",
                        or_(
                            WorkspaceBpmnReview.conformance_leased_at.is_(None),
                            WorkspaceBpmnReview.conformance_leased_at < expired_before,
                        ),
                    ),
                )
            )
            .order_by(WorkspaceBpmnReview.updated_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        claimed = []
        now = now_iso()
        for row in rows:
            if (row.conformance_attempts or 0) >= CONFORMANCE_MAX_ATTEMPTS:
                # Ha gia' avuto i suoi tentativi e nessuno e' arrivato in fondo:
                # esce dalla coda invece di girare per sempre, e resta contata.
                logger.warning(
                    "confronto con le fonti abbandonato per il processo %s dopo %s tentativi",
                    row.process_id,
                    row.conformance_attempts,
                )
                row.conformance_status = CONFORMANCE_FAILED
                row.conformance_leased_at = None
                continue
            row.conformance_status = "running"
            row.conformance_leased_at = now
            row.conformance_attempts = (row.conformance_attempts or 0) + 1
            claimed.append(
                {
                    "tenant_id": row.tenant_id,
                    "process_id": row.process_id,
                    "bpmn_model_id": row.bpmn_model_id,
                }
            )
        session.flush()
        return claimed


def enqueue_unchecked_conformance(limit: int = 20, *, only_tenant_id: str | None = None) -> list[str]:
    """Mette in coda i processi che hanno un disegno e non sono mai stati confrontati.

    La coda si riempie quando qualcuno disegna o rivede un piano. Da sola quella
    regola coprirebbe solo i processi toccati da quando il confronto esiste: tutti
    i disegni gia' sul tavolo - gli altri progetti, gli altri clienti - resterebbero
    senza verifica per sempre, e il pannello direbbe "non ancora confrontato"
    finche' qualcuno non li riapre. Qui entrano anche loro, un po' per passata.

    Args:
        limit: Quanti processi mettere in coda al massimo.
        only_tenant_id: Limita a un tenant (amministrazione, test).

    Returns:
        Gli id dei modelli messi in coda.
    """
    with workspace_connection() as session:
        statement = (
            select(WorkspaceBpmnReview)
            .join(WorkspaceBpmnModel, WorkspaceBpmnModel.id == WorkspaceBpmnReview.bpmn_model_id)
            .where(WorkspaceBpmnReview.conformance_status.is_(None))
            .where(WorkspaceBpmnModel.xml.is_not(None))
            .order_by(WorkspaceBpmnReview.updated_at)
            .limit(max(1, int(limit)))
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        for row in rows:
            _queue_conformance(row)
        session.flush()
        return [row.bpmn_model_id for row in rows]


# Per quanto una riga presa in carico resta invisibile agli altri worker. Piu'
# larga di quella dei piani perche' un confronto legge una fonte per volta con il
# modello: sui processi veri sono minuti, e una scadenza stretta farebbe lavorare
# due volte lo stesso disegno.
CONFORMANCE_LEASE_SECONDS = 900
# Prese in carico per lo stesso disegno prima di smettere. Con il lease da 15
# minuti sono piu' di un'ora di tentativi: abbastanza per un provider che torna,
# non abbastanza per riempire il log di un errore che non passera'.
CONFORMANCE_MAX_ATTEMPTS = 5
CONFORMANCE_FAILED = "failed"

# Lo stato di chi ha rinunciato: la review salvata non e' leggibile, e la coda
# non la ripropone. Non e' `done` - nessun confronto e' stato fatto - e non e'
# `pending`, altrimenti la stessa riga girerebbe per sempre. Torna in coda solo
# quando qualcuno tocca il piano (`request_conformance_check`).
CONFORMANCE_UNAVAILABLE = "unavailable"


def conformance_queue_stats(*, only_tenant_id: str | None = None) -> dict[str, int]:
    """Quanti confronti sono in attesa, presi in carico, o rinunciati.

    Args:
        only_tenant_id: Limita il conto a un tenant (amministrazione, test).
    """
    statement = select(WorkspaceBpmnReview.conformance_status, func.count()).group_by(
        WorkspaceBpmnReview.conformance_status
    )
    if only_tenant_id:
        statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
    with workspace_connection() as session:
        rows = session.execute(statement).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0),
        "stuck": counts.get("running", 0),
        # Disegni che la coda ha smesso di riprovare: il piano salvato non si
        # legge. Contarli separatamente e' l'unico modo per accorgersene, invece
        # di vederli sparire dentro "done" come se fossero stati confrontati.
        "unavailable": counts.get(CONFORMANCE_UNAVAILABLE, 0),
        # Disegni che hanno esaurito i tentativi: errori ripetuti, non un
        # piano illeggibile. Anche questi vanno guardati da una persona.
        "failed": counts.get(CONFORMANCE_FAILED, 0),
    }


def release_conformance_check(bpmn_model_id: str, *, status: str = "pending") -> None:
    """Rimette una presa in carico nello stato dato (riprova, o resa)."""
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is not None:
            review.conformance_status = status
            review.conformance_leased_at = None
            session.flush()


MATERIALIZATION_MAX_ATTEMPTS = 5
MATERIALIZATION_BACKOFF_SECONDS = 30
# Per quanto una riga presa in carico resta invisibile agli altri worker. Non e'
# uno stato `running` - un lease che nessuno rilascia e' il modo in cui una coda
# si blocca in silenzio - ma una scadenza: se chi l'ha presa muore, la riga torna
# eleggibile da sola.
MATERIALIZATION_LEASE_SECONDS = 300


def _materialization_to_dict(row: WorkspacePlanMaterialization) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "process_id": row.process_id,
        "status": row.status,
        "requested_at": row.requested_at,
        "reason": row.reason,
        "attempts": row.attempts,
        "next_attempt_at": row.next_attempt_at,
        "last_error": row.last_error,
        "completed_at": row.completed_at,
        "last_action": row.last_action,
        "plan_version": row.plan_version,
    }


def _plan_extraction_to_dict(row: WorkspacePlanExtraction) -> dict:
    return {
        "id": row.id,
        "artifact_key": row.artifact_key,
        "source_id": row.source_id,
        "source_name": row.source_name,
        "input_digest": row.input_digest,
        "prompt_version": row.prompt_version,
        "model": row.model,
        "plan": json.loads(row.plan_json or "{}"),
        "created_at": row.created_at,
    }


def plan_extractions_by_key(keys: list[str]) -> dict[str, dict]:
    """I piani parziali gia' estratti, fra quelli chiesti.

    Una query per tutta la sintesi, non una per fonte: con cinque interviste
    sarebbero cinque viaggi al database per rispondere a una domanda sola, e il
    punto di questo artefatto e' rendere una ricostruzione piu' economica.

    Args:
        keys: Le chiavi degli artefatti, non affidabili.

    Returns:
        Gli artefatti trovati, per chiave. Le chiavi assenti semplicemente non
        compaiono: non si sa distinguere "mai estratto" da "estratto e poi
        cancellato", e non serve saperlo.

    Sola lettura, dentro il tenant corrente.
    """
    wanted = [key for key in dict.fromkeys(keys) if key]
    if not wanted:
        return {}
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspacePlanExtraction)
                .where(WorkspacePlanExtraction.tenant_id == tenant_id())
                .where(WorkspacePlanExtraction.artifact_key.in_(wanted))
            )
            .scalars()
            .all()
        )
        return {row.artifact_key: _plan_extraction_to_dict(row) for row in rows}


def save_plan_extraction(
    *,
    artifact_key: str,
    plan: dict,
    source_id: str = "",
    source_name: str = "",
    input_digest: str = "",
    prompt_version: str = "",
    model: str = "",
) -> dict:
    """Registra il piano parziale ricavato da una fonte, una volta sola.

    Non e' una scrittura sul processo e non passa da `assert_write_allowed`:
    l'artefatto e' la registrazione di un lavoro gia' pagato, e una modalita' di
    chat che permette di estrarre ma non di prenderne nota farebbe ripagare la
    stessa estrazione al giro dopo.

    Riscrivere un artefatto gia' presente non ha senso - la chiave contiene
    tutto cio' che determina il risultato - quindi qui si tiene il primo. E'
    anche cio' che rende innocua la gara fra due sintesi dello stesso processo.

    Args:
        artifact_key: L'identita' dell'estrazione, non affidabile.
        plan: Il piano parziale, gia' serializzato in JSON.
        source_id: La fonte da cui veniva, per leggere la tabella.
        source_name: Il nome della fonte, idem.
        input_digest: L'impronta del testo letto.
        prompt_version: La versione del prompt che l'ha prodotto.
        model: Il modello che l'ha prodotto.

    Returns:
        L'artefatto salvato, o quello che c'era gia'.

    Raises:
        ValueError: Se la chiave e' vuota. Un artefatto senza identita' non si
            ritrova, e scriverlo riempirebbe la tabella di righe irraggiungibili.
    """
    key = str(artifact_key or "").strip()
    if not key:
        raise ValueError("Un artefatto di estrazione senza chiave non si ritrova.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing = (
            session.execute(
                select(WorkspacePlanExtraction)
                .where(WorkspacePlanExtraction.tenant_id == current_tenant_id)
                .where(WorkspacePlanExtraction.artifact_key == key)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return _plan_extraction_to_dict(existing)

        row = WorkspacePlanExtraction(
            tenant_id=current_tenant_id,
            artifact_key=key,
            source_id=str(source_id or ""),
            source_name=str(source_name or ""),
            input_digest=str(input_digest or ""),
            prompt_version=str(prompt_version or ""),
            model=str(model or ""),
            plan_json=json.dumps(plan, ensure_ascii=False),
            created_at=now_iso(),
        )
        session.add(row)
        session.flush()
        return _plan_extraction_to_dict(row)


def source_audits_by_key(keys: list[str]) -> dict[str, dict]:
    """I verdetti del revisore gia' pagati, fra quelli chiesti.

    Una query per tutto il confronto, non una per fonte, per la stessa ragione
    dei piani parziali.

    Args:
        keys: Le chiavi degli artefatti, non affidabili.

    Returns:
        I verdetti trovati, per chiave, come dizionari grezzi dell'agente.

    Sola lettura, dentro il tenant corrente.
    """
    wanted = [key for key in dict.fromkeys(keys) if key]
    if not wanted:
        return {}
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspaceSourceAudit)
                .where(WorkspaceSourceAudit.tenant_id == tenant_id())
                .where(WorkspaceSourceAudit.artifact_key.in_(wanted))
            )
            .scalars()
            .all()
        )
        return {row.artifact_key: json.loads(row.verdict_json or "{}") for row in rows}


def save_source_audit(
    *,
    artifact_key: str,
    verdict: dict,
    source_id: str = "",
    source_name: str = "",
    prompt_version: str = "",
    model: str = "",
) -> None:
    """Registra il verdetto del revisore su una fonte, una volta sola.

    Come per il piano parziale: la chiave contiene tutto cio' che determina il
    verdetto, quindi se c'e' gia' si tiene quello, e due confronti in gara sulla
    stessa fonte non si pestano.

    Raises:
        ValueError: Se la chiave e' vuota.
    """
    key = str(artifact_key or "").strip()
    if not key:
        raise ValueError("Un verdetto del revisore senza chiave non si ritrova.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing = (
            session.execute(
                select(WorkspaceSourceAudit.id)
                .where(WorkspaceSourceAudit.tenant_id == current_tenant_id)
                .where(WorkspaceSourceAudit.artifact_key == key)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return
        session.add(
            WorkspaceSourceAudit(
                tenant_id=current_tenant_id,
                artifact_key=key,
                source_id=str(source_id or ""),
                source_name=str(source_name or ""),
                prompt_version=str(prompt_version or ""),
                model=str(model or ""),
                verdict_json=json.dumps(verdict, ensure_ascii=False),
                created_at=now_iso(),
            )
        )
        session.flush()


def enqueue_plan_materialization(
    process_id: str | None,
    *,
    reason: str = "",
    session=None,
) -> dict | None:
    """Segna che il piano di questo processo va ricostruito.

    Non e' una scrittura sul processo: e' la registrazione di un lavoro da fare,
    e per questo non passa da `assert_write_allowed`. Salvare un'intervista e'
    permesso in ogni modalita' di chat, e una modalita' che permette di
    raccogliere evidenza ma non di prenderne nota lascerebbe il piano indietro
    senza che nessuno lo sappia.

    Una riga per processo. Se ce n'e' gia' una in attesa, `requested_at` si
    sposta in avanti e i tentativi ripartono: una fonte nuova rende di nuovo
    utile un lavoro che aveva fallito.

    Args:
        process_id: Il processo la cui evidenza e' cambiata; `None` non fa nulla
            (una fonte di progetto non appartiene a nessun processo).
        reason: Perche', per chi legge la coda.
        session: La sessione della scrittura che ha cambiato l'evidenza, quando
            c'e'. Passarla tiene coda e fonte nella stessa transazione: se il
            salvataggio della fonte torna indietro, la richiesta di
            ricostruzione torna indietro con lui.

    Returns:
        La riga di coda, o `None` se non c'era niente da mettere in coda.
    """
    if not process_id:
        return None

    def _upsert(active_session) -> dict:
        now = now_iso()
        current_tenant_id = tenant_id()
        row = (
            active_session.execute(
                select(WorkspacePlanMaterialization)
                .where(WorkspacePlanMaterialization.tenant_id == current_tenant_id)
                .where(WorkspacePlanMaterialization.process_id == process_id)
            )
            .scalars()
            .first()
        )
        if row is None:
            row = WorkspacePlanMaterialization(
                tenant_id=current_tenant_id,
                process_id=process_id,
                status="pending",
                requested_at=now,
                reason=reason,
                attempts=0,
                next_attempt_at=now,
            )
            active_session.add(row)
        else:
            row.status = "pending"
            row.requested_at = now
            row.reason = reason or row.reason
            row.attempts = 0
            row.next_attempt_at = now
            row.last_error = None
            row.completed_at = None
        active_session.flush()
        return _materialization_to_dict(row)

    if session is not None:
        return _upsert(session)

    with workspace_connection() as owned_session:
        return _upsert(owned_session)


def due_plan_materializations(limit: int = 5, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le richieste pronte, di tutti i tenant.

    Il worker gira fuori da una richiesta HTTP e quindi fuori da un tenant: la
    riga porta il proprio, e chi la lavora lo vincola prima di toccare il
    processo. Le piu' vecchie per prime, cosi' una richiesta non resta indietro
    perche' un altro processo continua a ricevere fonti.

    Non e' una lettura: le righe vengono prese in carico (`FOR UPDATE SKIP
    LOCKED` + scadenza spostata in avanti). Due worker - due istanze dell'app,
    o un worker separato accanto all'app - altrimenti sintetizzerebbero lo stesso
    piano due volte, e il processo si troverebbe due versioni nate dallo stesso
    evento.

    Args:
        limit: Quante righe prendere in carico.
        only_tenant_id: Limita la coda a un tenant. I test drenano cosi': una
            passata che prende la riga di un altro workspace lavorerebbe il
            processo di un cliente.

    Side effects:
        Sposta `next_attempt_at` di ogni riga presa in carico.
    """
    now = now_iso()
    lease_until = (
        datetime.now(UTC) + timedelta(seconds=MATERIALIZATION_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspacePlanMaterialization)
            .where(WorkspacePlanMaterialization.status == "pending")
            .where(WorkspacePlanMaterialization.next_attempt_at <= now)
            .order_by(WorkspacePlanMaterialization.next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(
                WorkspacePlanMaterialization.tenant_id == only_tenant_id
            )
        rows = session.execute(statement).scalars().all()
        claimed = [_materialization_to_dict(row) for row in rows]
        for row in rows:
            row.next_attempt_at = lease_until
        session.flush()
        return claimed


def _owned_materialization(session, materialization_id: int):
    """La riga di coda, se appartiene al tenant vincolato adesso.

    Il worker lavora righe di tenant diversi e l'id da solo non dice di chi sia:
    chiudere una riga senza guardare il tenant e' una scrittura fuori confine
    anche quando l'id viene dalla coda stessa, perche' fa dipendere l'isolamento
    dall'ordine delle chiamate invece che da un controllo.
    """
    row = session.get(WorkspacePlanMaterialization, materialization_id)
    if row is None or row.tenant_id != tenant_id():
        return None
    return row


def complete_plan_materialization(
    materialization_id: int,
    *,
    action: str,
    plan_version: int | None,
) -> dict | None:
    """La richiesta e' stata lavorata: cosa ne e' uscito resta scritto."""
    with workspace_connection() as session:
        row = _owned_materialization(session, materialization_id)
        if row is None:
            return None
        row.status = "done"
        row.completed_at = now_iso()
        row.last_error = None
        row.last_action = action
        row.plan_version = plan_version
        session.flush()
        return _materialization_to_dict(row)


def fail_plan_materialization(
    materialization_id: int,
    *,
    error: str,
    max_attempts: int = MATERIALIZATION_MAX_ATTEMPTS,
    backoff_seconds: int = MATERIALIZATION_BACKOFF_SECONDS,
) -> dict | None:
    """Un tentativo non riuscito: si riprova piu' tardi, ma non per sempre.

    Un guasto momentaneo - il modello in rate limit, il database occupato - si
    supera aspettando; un piano che non si riesce a costruire non migliora al
    quinto tentativo, e tenerlo in coda nasconderebbe che quel processo non ha
    un piano.
    """
    with workspace_connection() as session:
        row = _owned_materialization(session, materialization_id)
        if row is None:
            return None
        row.attempts += 1
        row.last_error = str(error)[:2000]
        if row.attempts >= max_attempts:
            row.status = "failed"
            row.completed_at = now_iso()
        else:
            delay = backoff_seconds * (2 ** (row.attempts - 1))
            row.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
        session.flush()
        return _materialization_to_dict(row)


def plan_materialization_for(process_id: str) -> dict | None:
    """La richiesta di ricostruzione di questo processo, se c'e'."""
    with workspace_connection() as session:
        row = (
            session.execute(
                select(WorkspacePlanMaterialization)
                .where(WorkspacePlanMaterialization.tenant_id == tenant_id())
                .where(WorkspacePlanMaterialization.process_id == process_id)
            )
            .scalars()
            .first()
        )
        return _materialization_to_dict(row) if row else None


def plan_materialization_stats() -> dict[str, int]:
    """Quante richieste sono in attesa e quante hanno smesso di riprovare."""
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspacePlanMaterialization.status, func.count())
            .group_by(WorkspacePlanMaterialization.status)
        ).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0),
        "stuck": counts.get("failed", 0),
    }


def enqueue_stale_plan_materializations(
    limit: int = 50, *, only_tenant_id: str | None = None
) -> list[dict]:
    """Mette in coda i processi il cui piano descrive un altro set di fonti.

    La coda si riempiva solo quando una fonte veniva creata con un processo. Due
    strade la lasciavano vuota, e il piano indietro per sempre:

    - le fonti registrate prima che la coda esistesse (il processo Esaote: tre
      interviste agli atti, un piano V1 preparato dal titolo, nessuna riga in
      coda, sei bozze start -> end);
    - le fonti di progetto, che valgono per ogni processo del progetto ma non
      nominano un processo da mettere in coda.

    Qui si confronta, per ogni processo con fonti, il set su cui il piano e' nato
    con quello che c'e' adesso, usando la stessa identita' del registro
    dell'evidenza. Tutti i tenant: gira nel worker, e la riga porta il suo.

    Una riga `failed` non si rimette in coda: e' un piano che non si riesce a
    costruire, e riprovarlo a ogni passata nasconderebbe proprio quello. Una riga
    `pending` c'e' gia'.

    Args:
        limit: Quante righe mettere in coda al massimo in una passata.
        only_tenant_id: Limita lo sweep a un tenant (amministrazione, test).

    Returns:
        Le righe messe in coda.
    """
    from backend.graphs.process.nodes import source_set_identity
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    with workspace_connection() as session:
        statement = select(WorkspaceProcess).where(WorkspaceProcess.archived_at.is_(None))
        if only_tenant_id:
            statement = statement.where(WorkspaceProcess.tenant_id == only_tenant_id)
        processes = session.execute(statement).scalars().all()
        sources_by_project: dict[tuple[str, str], list[dict]] = {}
        for source in session.execute(select(WorkspaceSource)).scalars():
            sources_by_project.setdefault((source.tenant_id, source.project_id), []).append(
                source_to_dict(source)
            )
        reviews = {
            (review.tenant_id, review.bpmn_model_id): review.evidence_source_set_id
            for review in session.execute(select(WorkspaceBpmnReview)).scalars()
        }
        queue = {
            (row.tenant_id, row.process_id): row.status
            for row in session.execute(select(WorkspacePlanMaterialization)).scalars()
        }

        stale: list[tuple[str, str]] = []
        for process in processes:
            key = (process.tenant_id, process.id)
            if queue.get(key) in {"pending", "failed"}:
                continue
            sources = [
                item
                for item in sources_by_project.get((process.tenant_id, process.project_id), [])
                if item.get("process_id") in {None, process.id}
            ]
            if not sources:
                continue
            recorded = reviews.get((process.tenant_id, process.bpmn_model_id))
            if recorded == source_set_identity(sources):
                continue
            stale.append(key)
            if len(stale) >= max(1, int(limit)):
                break

    queued: list[dict] = []
    for owner_tenant, process_id in stale:
        token = set_current_tenant_id(owner_tenant)
        try:
            row = enqueue_plan_materialization(
                process_id, reason="piano costruito su un set di fonti diverso da quello agli atti"
            )
        finally:
            reset_current_tenant_id(token)
        if row:
            queued.append(row)
    return queued


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
