import json
import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.agents.chat_mode import assert_write_allowed
from backend.process_understanding import (
    ProcessUnderstanding,
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
    WorkspaceClient,
    WorkspaceDecision,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSimulationRun,
    WorkspaceSimulationRunArtifact,
    WorkspaceSource,
    workspace_connection,
)


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


def list_clients(include_archived: bool = False) -> list[dict]:
    """List clients belonging to the current tenant in name order.

    Args:
        include_archived: Include closed clients. Off by default: the directory
            is the work in progress, not everything that ever happened.

    Returns:
        list[dict]: Tenant-scoped client records sorted by name.
    """
    with workspace_connection() as session:
        statement = (
            select(WorkspaceClient)
            .where(WorkspaceClient.tenant_id == tenant_id())
            .order_by(WorkspaceClient.name)
        )
        if not include_archived:
            statement = statement.where(WorkspaceClient.archived_at.is_(None))
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


def list_projects(include_archived: bool = False) -> list[dict]:
    with workspace_connection() as session:
        statement = (
            select(WorkspaceProject)
            .where(WorkspaceProject.tenant_id == tenant_id())
            .order_by(WorkspaceProject.name)
        )
        if not include_archived:
            statement = statement.where(WorkspaceProject.archived_at.is_(None))
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
        }


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
) -> dict | None:
    """
    Persist an authorized BPMN model update and create a version snapshot.
    
    Args:
        bpmn_model_id (str): Tenant-scoped model identifier.
        xml (str): Untrusted BPMN XML content; it must contain non-whitespace
            characters.
        change_summary (str): Untrusted description of the change.
        source (str): Untrusted origin label for the version snapshot.
    
    Returns:
        dict | None: The updated model data, or `None` when the model does not
        belong to the current tenant or does not exist.
    
    Raises:
        PermissionError: If the caller is not authorized to write BPMN models.
        ValueError: If `xml` is empty or contains only whitespace.
    
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

        model.xml = clean_xml
        create_bpmn_version(
            session=session,
            model=model,
            xml=clean_xml,
            change_summary=change_summary,
            source=source,
        )
        session.flush()
        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
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

        model.xml = version.xml
        restored = create_bpmn_version(
            session=session,
            model=model,
            xml=version.xml,
            change_summary=f"Ripristino versione {version_id}",
            source="restore",
        )
        session.flush()
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
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


def _review_artifacts(review) -> tuple[dict, dict]:
    """Validate and derive artifacts from a stored BPMN review.
    
    Args:
        review: Untrusted stored review row containing serialized semantic-model data.
    
    Returns:
        A tuple containing the canonical semantic model and its recomputed quality
        report.
    
    Raises:
        ValueError: If the stored semantic model is invalid or lacks the required
            compilation plan or source understanding.
        (json.JSONDecodeError, pydantic.ValidationError): If the stored payload or
            process understanding cannot be decoded or validated.
    
    The function does not persist changes or otherwise modify the review.
    """
    bpmn_semantic_model = json.loads(review.bpmn_semantic_model_json or "{}")
    if not _is_canonical_semantic_model_payload(bpmn_semantic_model):
        raise ValueError("Review BPMN legacy rifiutata: semantic model non canonicale.")
    process_understanding = bpmn_semantic_model.get("sourceProcessUnderstanding") or {}
    quality_report = quality_report_from_understanding(
        ProcessUnderstanding.model_validate(process_understanding)
    ).model_dump(mode="json")
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
        "open_questions": open_questions_with_answers(review),
        "answers": decode_answers(review),
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


def prepare_bpmn_review(
    bpmn_model_id: str,
    process_description: str,
    process_understanding: dict | None = None,
) -> dict:
    """Prepare and persist a pending BPMN review for a model.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier. The model must belong to
            the current tenant.
        process_description (str): Untrusted process description. It must contain
            non-whitespace text.
        process_understanding (dict | None): Untrusted optional process understanding
            used to generate the review draft.
    
    Returns:
        dict: The serialized, pending BPMN review.
    
    Raises:
        ValueError: If the process description is empty or the BPMN model cannot be
            found for the current tenant.
    
    The review is persisted in the workspace. A new review starts at version 1;
    preparing an existing review creates its next version while preserving the
    previous snapshot.
    """
    clean_text = process_description.strip()
    if not clean_text:
        raise ValueError("Descrizione processo obbligatoria.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

        bpmn_process_id = f"Process_{slugify(model.process.name, 'process').replace('-', '_')}"
        review_draft = build_bpmn_review_draft(
            bpmn_process_id=bpmn_process_id,
            process_name=model.process.name,
            source_text=clean_text,
            process_understanding=process_understanding,
        )

        timestamp = now_iso()
        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") != current_tenant_id:
            review = None

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
            review.status = "pending"
            review.updated_at = timestamp

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
    return {
        "id": source.id,
        "project_id": source.project_id,
        "process_id": source.process_id,
        "name": source.name,
        "type": source.type,
        "meta": source.meta,
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


def list_project_sources(project_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            return []

        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.project_id == project_id)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .order_by(WorkspaceSource.name)
        )
        sources = session.execute(statement).scalars().all()
        return [source_to_dict(source) for source in sources]


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


def create_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
) -> dict:
    _assert_source_scope(project_id, process_id)
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
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
            process_id=process_id,
            name=name.strip(),
            type=type.strip() or "Fonte",
            meta=meta.strip(),
        )
        session.add(source)
        session.flush()
        return source_to_dict(source)


def ensure_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
) -> tuple[dict, bool]:
    """Registra una fonte una volta sola, per nome, dentro il suo processo.

    Un'intervista salvata due volte dalla chat - il consulente riformula, il
    turno viene ripetuto - non deve diventare due voci nel pannello Fonti. La
    fonte esistente viene restituita com'e': il record dice quando l'evidenza e'
    entrata nel progetto, e riscriverlo a ogni salvataggio cancellerebbe quel
    fatto.

    Args:
        project_id: Progetto proprietario, non affidabile.
        name: Nome della fonte come la legge il consulente, non affidabile.
        type: Etichetta del tipo, gia' tradotta per chi legge.
        meta: Nota in prosa sulla fonte.
        process_id: Processo a cui l'evidenza appartiene, quando c'e'.

    Returns:
        La fonte e se e' stata creata adesso (``False`` se esisteva gia').

    Raises:
        ValueError: Se il progetto non esiste o il processo non e' suo.
        ScopeViolation: Se progetto o processo non sono quelli autorizzati per
            il turno di chat corrente.

    Scrive nel workspace solo quando la fonte non esiste.
    """
    _assert_source_scope(project_id, process_id)
    cleaned_name = name.strip()
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        existing = (
            session.execute(
                select(WorkspaceSource)
                .where(WorkspaceSource.project_id == project_id)
                .where(WorkspaceSource.tenant_id == tenant_id())
                .where(WorkspaceSource.process_id == process_id)
                .where(func.lower(WorkspaceSource.name) == cleaned_name.lower())
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return source_to_dict(existing), False

    return (
        create_project_source(
            project_id=project_id,
            name=cleaned_name,
            type=type,
            meta=meta,
            process_id=process_id,
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
    """Elimina un cliente e tutto cio' che ne dipende. Non si torna indietro."""
    assert_write_allowed("eliminare un cliente")

    with workspace_connection() as session:
        client = _client_or_raise(session, client_id)
        removed = {"id": client.id, "name": client.name, **_record_counts(session, client=client)}
        for project in list(client.projects):
            _purge_project(session, project)
        session.delete(client)
        session.flush()
        return removed


def delete_project(project_id: str) -> dict:
    """Elimina un progetto, i suoi processi, fonti e decisioni."""
    assert_write_allowed("eliminare un progetto")

    with workspace_connection() as session:
        project = _project_or_raise(session, project_id)
        removed = {
            "id": project.id,
            "name": project.name,
            **_record_counts(session, project=project),
        }
        _purge_project(session, project)
        session.flush()
        return removed


def delete_process(process_id: str) -> dict:
    """Elimina un processo, il suo modello BPMN e le fonti che vi puntavano."""
    assert_write_allowed("eliminare un processo")

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
        _purge_process(session, process)
        if project.archived_at is None:
            project.process_count = max(0, project.process_count - 1)
        session.flush()
        return removed


def _purge_process(session, process: WorkspaceProcess) -> None:
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
            session.delete(row)

    session.delete(process)


def _purge_project(session, project: WorkspaceProject) -> None:
    """Toglie un progetto, i suoi processi e i record che vi appartengono."""
    for process in list(project.processes):
        _purge_process(session, process)

    for model, column in (
        (WorkspaceSource, WorkspaceSource.project_id),
        (WorkspaceDecision, WorkspaceDecision.project_id),
    ):
        for row in session.execute(select(model).where(column == project.id)).scalars():
            session.delete(row)

    session.delete(project)


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
                session.delete(row)
