"""Clienti, incarichi e processi: crearli, leggerli, aggiornarli, con i limiti
sulle liste.
"""

from sqlalchemy import Select, func, select

from backend.workspace_database._common import decode_list, decode_milestones, encode_list, encode_milestones, normalize_name, slugify, tenant_id, tenant_row, unique_id
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
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceClient,
    WorkspaceProcess,
    WorkspaceProject,
    workspace_connection,
)


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


def clients_statement(include_archived: bool) -> Select[tuple[WorkspaceClient]]:
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


def projects_statement(include_archived: bool) -> Select[tuple[WorkspaceProject]]:
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
