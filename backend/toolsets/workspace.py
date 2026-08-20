from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.toolsets.common import format_workspace_result


def enterprise_tool_result(
    *,
    status: str,
    action: str,
    entity_type: str,
    summary: str,
    entity_id: str | None = None,
    payload: dict | list | None = None,
    warnings: list[str] | None = None,
    next_actions: list[dict] | None = None,
) -> str:
    return format_workspace_result(
        action,
        {
            "status": status,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "payload": payload or {},
            "warnings": warnings or [],
            "next_actions": next_actions or [],
        },
    )


class HomeDashboardUpdateInput(BaseModel):
    summary: str = Field(description="Concise dashboard summary to show in Home.")
    priorities: list[str] = Field(default_factory=list, description="Priority items for the consultant.")
    risks: list[str] = Field(default_factory=list, description="Workspace-level risks or blockers.")
    next_actions: list[str] = Field(default_factory=list, description="Concrete next actions to surface.")


class HomeItemInput(BaseModel):
    title: str = Field(description="Short reader-facing item title.")
    reason: str = Field(description="Why this item matters now.")
    owner: str = Field(default="Consult Macro Agent", description="Owner or responsible scope.")
    related_entity_id: str | None = Field(default=None, description="Optional related client/project/process id.")


class ClientRecordInput(BaseModel):
    operation: str = Field(description="Use create, inspect, or summarize. Do not use for hypothetical examples.")
    name: str = Field(description="Client name.")
    sector: str = Field(default="Non specificato", description="Client sector when known.")
    status: str = Field(default="Prospect", description="Client status.")
    owner: str = Field(default="Da assegnare", description="Client owner.")
    contact: str = Field(default="", description="Non-sensitive contact note when provided.")


class InitialWorkspaceSetupInput(BaseModel):
    client_name: str = Field(description="Client name for setup.")
    project_name: str | None = Field(default=None, description="Initial project name, if requested.")
    process_name: str | None = Field(default=None, description="Initial process stub name, if requested.")
    source_name: str | None = Field(default=None, description="Initial source/evidence name, if requested.")
    decision_title: str | None = Field(default=None, description="Initial open decision title, if requested.")
    reason: str = Field(description="Why this setup should be created now.")
    client_sector: str = Field(default="Non specificato", description="Client sector when known.")
    client_status: str = Field(default="Prospect", description="Client status.")
    client_owner: str = Field(default="Da assegnare", description="Client owner.")


@tool
def get_workspace_overview() -> str:
    """
    Read a compact global workspace overview for consultant-level synthesis and routing.
    Use in Consulting/Home scope before giving cross-client or cross-project priorities,
    risks, next actions, or setup recommendations. This is read-only.
    """
    clients = workspace_database.list_clients()
    projects = workspace_database.list_projects()
    active_projects = [project for project in projects if project.get("status") != "Archiviato"]
    open_issues = [
        {"project_id": project["id"], "project": project["name"], "issue": issue}
        for project in projects
        for issue in project.get("open_issues", [])
    ]
    next_steps = [
        {
            "project_id": project["id"],
            "project": project["name"],
            "client": project["client"],
            "next_step": project["next_step"],
        }
        for project in active_projects
        if project.get("next_step")
    ]

    return format_workspace_result(
        "Workspace overview",
        {
            "client_count": len(clients),
            "project_count": len(projects),
            "active_project_count": len(active_projects),
            "clients": clients,
            "projects": projects,
            "open_issues": open_issues,
            "next_steps": next_steps,
        },
    )


@tool(args_schema=HomeDashboardUpdateInput)
def prepare_home_dashboard_update(
    summary: str,
    priorities: list[str] | None = None,
    risks: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> str:
    """
    Purpose: prepare a structured Home dashboard update without mutating workspace records.
    Use when the Home subgraph must turn workspace context into priorities, risks and next actions.
    Do not use for client/project/process/canvas mutations.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_home_dashboard_update",
        entity_type="home_dashboard",
        summary=summary,
        payload={
            "summary": summary,
            "priorities": priorities or [],
            "risks": risks or [],
            "next_actions": next_actions or [],
        },
    )


@tool(args_schema=HomeItemInput)
def record_home_priority(
    title: str,
    reason: str,
    owner: str = "Consult Macro Agent",
    related_entity_id: str | None = None,
) -> str:
    """
    Purpose: prepare one Home priority item in a standard enterprise payload.
    Use when the Home subgraph identifies something the consultant should focus on.
    This does not persist a database record yet; it returns a structured item for state/UI handoff.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_home_priority",
        entity_type="home_priority",
        entity_id=related_entity_id,
        summary=title,
        payload={
            "title": title,
            "reason": reason,
            "owner": owner,
            "related_entity_id": related_entity_id,
        },
    )


@tool(args_schema=HomeItemInput)
def record_home_risk(
    title: str,
    reason: str,
    owner: str = "Consult Macro Agent",
    related_entity_id: str | None = None,
) -> str:
    """
    Purpose: prepare one Home risk or blocker in a standard enterprise payload.
    Use when the Home subgraph finds stalled work, ambiguity, missing owner or delivery risk.
    This does not persist a database record yet; it returns a structured item for state/UI handoff.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_home_risk",
        entity_type="home_risk",
        entity_id=related_entity_id,
        summary=title,
        payload={
            "title": title,
            "reason": reason,
            "owner": owner,
            "related_entity_id": related_entity_id,
        },
    )


@tool(args_schema=HomeItemInput)
def record_next_action(
    title: str,
    reason: str,
    owner: str = "Consult Macro Agent",
    related_entity_id: str | None = None,
) -> str:
    """
    Purpose: prepare one next action with owner and rationale.
    Use when a subgraph needs to hand back a clear action item to the Consulting Chat or Home UI.
    This does not persist a database record yet; it returns a structured item for state/UI handoff.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_next_action",
        entity_type="next_action",
        entity_id=related_entity_id,
        summary=title,
        payload={
            "title": title,
            "reason": reason,
            "owner": owner,
            "related_entity_id": related_entity_id,
        },
    )


@tool
def list_workspace_clients() -> str:
    """
    List clients currently present in the workspace database.
    Use before creating a client when the user references a client that may already exist.
    """
    return format_workspace_result("Clienti workspace", workspace_database.list_clients())


@tool
def list_workspace_projects() -> str:
    """
    List projects currently present in the workspace database, including their ids.
    Use before creating a process/source/decision when you need the project_id.
    """
    return format_workspace_result("Progetti workspace", workspace_database.list_projects())


@tool
def get_workspace_project(project_id: str) -> str:
    """
    Read one project with its client, process list, milestones, open issues and deliverables.
    Use when you already have a project_id and need current project context before acting.
    """
    project = workspace_database.get_project(project_id)

    if project is None:
        raise ValueError(f"Progetto non trovato: {project_id}")

    return format_workspace_result("Progetto workspace", project)


@tool
def list_workspace_project_processes(project_id: str) -> str:
    """
    List processes for one project, including process_id and bpmn_model_id.
    Use before creating a duplicate process or when routing the user to a process/canvas scope.
    """
    return format_workspace_result(
        "Processi progetto workspace",
        workspace_database.list_project_processes(project_id),
    )


@tool
def get_workspace_process(process_id: str) -> str:
    """
    Read one process record, including its project_id and bpmn_model_id.
    Use when you need current process context before collecting AS-IS information or BPMN work.
    """
    process = workspace_database.get_process(process_id)

    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    return format_workspace_result("Processo workspace", process)


@tool
def get_workspace_bpmn_model(bpmn_model_id: str) -> str:
    """
    Read BPMN model metadata and whether saved XML exists.
    Use when you need to confirm a canvas/model id. Use BPMN-specific tools to inspect XML.
    """
    model = workspace_database.get_bpmn_model(bpmn_model_id)

    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Modello BPMN workspace",
        {
            "id": model["id"],
            "process_id": model["process_id"],
            "name": model["name"],
            "has_xml": bool(model["xml"]),
        },
    )


@tool
def get_workspace_bpmn_review(bpmn_model_id: str) -> str:
    """
    Read a pending BPMN review for a model.
    Use after preparing an AS-IS/BPMN review or before asking the user for approval/corrections.
    """
    review = workspace_database.get_bpmn_review(bpmn_model_id)

    if review is None:
        return format_workspace_result(
            "Review BPMN workspace",
            {"bpmn_model_id": bpmn_model_id, "review_pending": False},
        )

    return format_workspace_result("Review BPMN workspace", review)


@tool
def create_workspace_client(
    name: str,
    sector: str = "Non specificato",
    status: str = "Prospect",
    owner: str = "Da assegnare",
    contact: str = "",
) -> str:
    """
    Create a client in the workspace database.
    Use only when the user asks to create or set up a real client record.
    Do not use for hypothetical examples.
    """
    client = workspace_database.create_client(
        name=name,
        sector=sector,
        status=status,
        owner=owner,
        contact=contact,
    )
    return format_workspace_result("Cliente creato", client)


@tool(args_schema=ClientRecordInput)
def manage_client_record(
    operation: str,
    name: str,
    sector: str = "Non specificato",
    status: str = "Prospect",
    owner: str = "Da assegnare",
    contact: str = "",
) -> str:
    """
    Purpose: manage a client record through one LLM-friendly facade.
    Use for explicit real client work from the Clients subgraph.
    Supported operations: create, inspect, summarize.
    It checks existing clients before creating to avoid duplicates.
    Do not use for project execution, process discovery, canvas work, or hypothetical examples.
    """
    normalized_operation = operation.strip().lower()
    clients = workspace_database.list_clients()
    existing = next(
        (
            client
            for client in clients
            if " ".join(client["name"].casefold().split()) == " ".join(name.casefold().split())
        ),
        None,
    )

    if normalized_operation in {"inspect", "summarize"}:
        if existing is None:
            return enterprise_tool_result(
                status="not_found",
                action="manage_client_record",
                entity_type="client",
                summary=f"Cliente non trovato: {name}",
                warnings=["No matching client record exists."],
            )

        return enterprise_tool_result(
            status="ok",
            action="manage_client_record",
            entity_type="client",
            entity_id=existing["id"],
            summary=f"Cliente trovato: {existing['name']}",
            payload=existing,
        )

    if normalized_operation != "create":
        return enterprise_tool_result(
            status="error",
            action="manage_client_record",
            entity_type="client",
            summary=f"Operazione cliente non supportata: {operation}",
            warnings=["Use one of: create, inspect, summarize."],
        )

    if existing is not None:
        return enterprise_tool_result(
            status="exists",
            action="manage_client_record",
            entity_type="client",
            entity_id=existing["id"],
            summary=f"Cliente gia presente: {existing['name']}",
            payload=existing,
            warnings=["Existing client returned instead of creating a duplicate."],
        )

    client = workspace_database.create_client(
        name=name,
        sector=sector,
        status=status,
        owner=owner,
        contact=contact,
    )
    return enterprise_tool_result(
        status="created",
        action="manage_client_record",
        entity_type="client",
        entity_id=client["id"],
        summary=f"Cliente creato: {client['name']}",
        payload=client,
    )


@tool
def create_workspace_project(
    client_id: str,
    name: str,
    phase: str = "Discovery",
    status: str = "Bozza",
    progress: int = 0,
    next_step: str = "Definire perimetro e fonti iniziali",
    milestones: list[str] | None = None,
    open_issues: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> str:
    """
    Create a project for an existing client in the workspace database.
    Use after you know the client_id. If the client does not exist, create the client first.
    """
    project = workspace_database.create_project(
        client_id=client_id,
        name=name,
        phase=phase,
        status=status,
        progress=progress,
        next_step=next_step,
        milestones=milestones,
        open_issues=open_issues,
        deliverables=deliverables,
    )
    return format_workspace_result("Progetto creato", project)


@tool
def create_workspace_process(
    project_id: str,
    name: str,
    stage: str = "AS-IS",
    status: str = "Bozza",
    owner: str = "Da assegnare",
    readiness: int = 0,
) -> str:
    """
    Create a process inside an existing project.
    Use for AS-IS/TO-BE process records. This creates the process record and its empty BPMN model.
    It does not generate BPMN XML.
    """
    process = workspace_database.create_process(
        project_id=project_id,
        name=name,
        stage=stage,
        status=status,
        owner=owner,
        readiness=readiness,
    )
    return format_workspace_result("Processo creato", process)


@tool
def list_workspace_project_sources(project_id: str) -> str:
    """
    List sources/evidence already recorded for a project.
    Use before adding evidence or when the user asks what material is linked to a project.
    """
    return format_workspace_result(
        "Fonti progetto workspace",
        workspace_database.list_project_sources(project_id),
    )


@tool
def add_workspace_source(
    project_id: str,
    name: str,
    type: str = "Fonte",
    meta: str = "",
    process_id: str | None = None,
) -> str:
    """
    Add a source/evidence item to a project, optionally linked to a process.
    Use for uploaded documents, interview notes, audio references, CSV exports, or other evidence.
    """
    source = workspace_database.create_project_source(
        project_id=project_id,
        name=name,
        type=type,
        meta=meta,
        process_id=process_id,
    )
    return format_workspace_result("Fonte aggiunta", source)


@tool
def list_workspace_project_decisions(project_id: str) -> str:
    """
    List decisions/open points already recorded for a project.
    Use before adding a decision or when the user asks for pending decisions.
    """
    return format_workspace_result(
        "Decisioni progetto workspace",
        workspace_database.list_project_decisions(project_id),
    )


@tool
def add_workspace_decision(
    project_id: str,
    title: str,
    owner: str = "Da assegnare",
    status: str = "Aperta",
    process_id: str | None = None,
) -> str:
    """
    Add a project or process decision/open decision to the workspace.
    Use when the user asks to record a decision, open point, or pending validation.
    """
    decision = workspace_database.create_project_decision(
        project_id=project_id,
        title=title,
        owner=owner,
        status=status,
        process_id=process_id,
    )
    return format_workspace_result("Decisione aggiunta", decision)


@tool(args_schema=InitialWorkspaceSetupInput)
def validate_initial_workspace_setup(
    client_name: str,
    project_name: str | None = None,
    process_name: str | None = None,
    source_name: str | None = None,
    decision_title: str | None = None,
    reason: str = "",
    client_sector: str = "Non specificato",
    client_status: str = "Prospect",
    client_owner: str = "Da assegnare",
) -> str:
    """
    Purpose: validate an explicit initial workspace setup before creating records.
    Use in Setup subgraph before create_initial_workspace_setup.
    It checks missing required setup pieces and duplicate client/project candidates.
    This tool is read-only.
    """
    warnings = []
    clients = workspace_database.list_clients()
    projects = workspace_database.list_projects()
    existing_client = next(
        (
            client
            for client in clients
            if " ".join(client["name"].casefold().split()) == " ".join(client_name.casefold().split())
        ),
        None,
    )
    existing_project = None

    if project_name:
        existing_project = next(
            (
                project
                for project in projects
                if " ".join(project["name"].casefold().split()) == " ".join(project_name.casefold().split())
            ),
            None,
        )

    if not client_name.strip():
        warnings.append("Client name is required.")
    if not reason.strip():
        warnings.append("Setup reason is missing; confirm this is a real workspace setup.")
    if existing_client is not None:
        warnings.append(f"Client already exists: {existing_client['id']}.")
    if existing_project is not None:
        warnings.append(f"Project already exists: {existing_project['id']}.")

    return enterprise_tool_result(
        status="valid" if not warnings else "review_required",
        action="validate_initial_workspace_setup",
        entity_type="workspace_setup",
        entity_id=existing_client["id"] if existing_client else None,
        summary="Initial workspace setup validated." if not warnings else "Initial setup needs review.",
        payload={
            "client_name": client_name,
            "project_name": project_name,
            "process_name": process_name,
            "source_name": source_name,
            "decision_title": decision_title,
            "reason": reason,
            "existing_client": existing_client,
            "existing_project": existing_project,
        },
        warnings=warnings,
    )


@tool(args_schema=InitialWorkspaceSetupInput)
def create_initial_workspace_setup(
    client_name: str,
    project_name: str | None = None,
    process_name: str | None = None,
    source_name: str | None = None,
    decision_title: str | None = None,
    reason: str = "",
    client_sector: str = "Non specificato",
    client_status: str = "Prospect",
    client_owner: str = "Da assegnare",
) -> str:
    """
    Purpose: create a minimal initial workspace setup in one controlled operation.
    Use only when the user explicitly asks to register real setup records.
    Creates or reuses the client, then optionally creates project, process stub, source and decision.
    Stop after setup; ongoing execution belongs to Project, Process or Canvas macro agents.
    """
    warnings = []
    created_records = []
    reused_records = []

    client = workspace_database.create_client(
        name=client_name,
        sector=client_sector,
        status=client_status,
        owner=client_owner,
    )
    clients = workspace_database.list_clients()
    matching_clients = [
        item
        for item in clients
        if " ".join(item["name"].casefold().split()) == " ".join(client_name.casefold().split())
    ]
    if len(matching_clients) > 1:
        warnings.append("Multiple matching clients exist after setup.")
    if client:
        reused_records.append({"entity_type": "client", "entity_id": client["id"], "name": client["name"]})

    project = None
    if project_name:
        existing_projects = workspace_database.list_projects()
        project = next(
            (
                item
                for item in existing_projects
                if " ".join(item["name"].casefold().split()) == " ".join(project_name.casefold().split())
            ),
            None,
        )
        if project is None:
            project = workspace_database.create_project(
                client_id=client["id"],
                name=project_name,
                next_step="Definire perimetro e fonti iniziali",
            )
            created_records.append({"entity_type": "project", "entity_id": project["id"], "name": project["name"]})
        else:
            reused_records.append({"entity_type": "project", "entity_id": project["id"], "name": project["name"]})

    process = None
    if process_name:
        if project is None:
            warnings.append("Process stub skipped because no project_name was provided.")
        else:
            process = workspace_database.create_process(project_id=project["id"], name=process_name)
            created_records.append(
                {"entity_type": "process", "entity_id": process["id"], "name": process["name"]}
            )

    if source_name:
        if project is None:
            warnings.append("Source skipped because no project_name was provided.")
        else:
            source = workspace_database.create_project_source(
                project_id=project["id"],
                process_id=process["id"] if process else None,
                name=source_name,
                type="Fonte",
                meta=reason,
            )
            created_records.append(
                {"entity_type": "source", "entity_id": source["id"], "name": source["name"]}
            )

    if decision_title:
        if project is None:
            warnings.append("Decision skipped because no project_name was provided.")
        else:
            decision = workspace_database.create_project_decision(
                project_id=project["id"],
                process_id=process["id"] if process else None,
                title=decision_title,
            )
            created_records.append(
                {"entity_type": "decision", "entity_id": decision["id"], "title": decision["title"]}
            )

    return enterprise_tool_result(
        status="created",
        action="create_initial_workspace_setup",
        entity_type="workspace_setup",
        entity_id=project["id"] if project else client["id"],
        summary="Initial workspace setup completed.",
        payload={
            "reason": reason,
            "client": client,
            "project": project,
            "process": process,
            "created_records": created_records,
            "reused_records": reused_records,
        },
        warnings=warnings,
        next_actions=[
            {
                "owner": "Project Macro Agent" if project else "Consult Macro Agent",
                "action": "Continue operational work in the correct macro scope.",
            }
        ],
    )


workspace_read_tools = [
    get_workspace_overview,
    list_workspace_clients,
    list_workspace_projects,
    get_workspace_project,
    list_workspace_project_processes,
    get_workspace_process,
    get_workspace_bpmn_model,
    get_workspace_bpmn_review,
    list_workspace_project_sources,
    list_workspace_project_decisions,
]

workspace_mutation_tools = [
    create_workspace_client,
    create_workspace_project,
    create_workspace_process,
    add_workspace_source,
    add_workspace_decision,
]

workspace_project_tools = [
    *workspace_read_tools,
    *workspace_mutation_tools,
]

workspace_process_tools = [
    *workspace_read_tools,
    create_workspace_process,
    add_workspace_source,
    add_workspace_decision,
]

workspace_canvas_tools = [
    *workspace_read_tools,
    add_workspace_source,
    add_workspace_decision,
]
