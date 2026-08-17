from langchain_core.tools import tool

from backend import workspace_database
from backend.toolsets.common import format_workspace_result


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


workspace_read_tools = [
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
