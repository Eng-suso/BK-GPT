import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.toolsets.memory import extract_playbook_from_episodes
from backend.toolsets.project_memory import (
    extract_project_graph_from_evidence,
    manage_project_evidence,
    retrieve_cross_process_impact_context,
    retrieve_project_gap_context,
    retrieve_project_graph_context,
)
from backend.toolsets.workspace import enterprise_tool_result


class ProjectProcessRecordInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    name: str = Field(description="Process name as the consultant named it.")
    stage: str = Field(
        default="AS-IS",
        description="AS-IS or TO-BE. Use AS-IS unless the consultant asked for a target process.",
    )
    owner: str = Field(
        default="Da assegnare",
        description="Owner or business area, only when the consultant named one. Do not guess.",
    )
    scope_note: str = Field(
        default="",
        description=(
            "The perimeter the consultant stated - start, end, what is in and out. "
            "Use their words. Leave empty when they did not state one."
        ),
    )


class ProjectDelegationPayloadInput(BaseModel):
    target_owner: str = Field(
        description="Destination owner: delivery, process_coordination, process_macro, or canvas_macro."
    )
    user_request: str = Field(description="Latest user request to delegate.")
    expected_result: str = Field(description="What the receiving owner should produce.")
    reason: str = Field(description="Why this owner is responsible.")
    known_context: str = Field(default="", description="Minimal project/process ids or facts needed for handoff.")


class ProjectStatusUpdateInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    summary: str = Field(description="Concise project status summary.")
    phase: str | None = Field(default=None, description="Suggested project phase, if changing.")
    status: str | None = Field(default=None, description="Suggested project status, if changing.")
    progress: int | None = Field(default=None, description="Suggested progress 0-100, if changing.")
    next_step: str | None = Field(default=None, description="Suggested next step, if changing.")
    risks: list[str] = Field(default_factory=list, description="Project-level risks or blockers.")
    next_actions: list[str] = Field(default_factory=list, description="Concrete project-level next actions.")


class ProjectItemInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    title: str = Field(description="Short reader-facing item title.")
    reason: str = Field(description="Why this item matters now.")
    owner: str = Field(default="Da assegnare", description="Owner or responsible scope.")
    severity: str = Field(default="medium", description="For risks: low, medium, high, or critical.")


class DeliverablePlanInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    objective: str = Field(description="Delivery objective for this plan.")
    deliverables: list[str] = Field(default_factory=list, description="Deliverables to prepare or validate.")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions behind the plan.")
    next_actions: list[str] = Field(default_factory=list, description="Actions needed to move deliverables forward.")


class DependencyIdentificationInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    relationship_hints: list[str] = Field(
        default_factory=list,
        description="User-provided or evidence-backed dependency hints between project processes.",
    )
    reason: str = Field(description="Why dependency analysis is needed now.")


class ProcessWorkplanInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    objective: str = Field(description="Coordination objective across processes.")
    focus_order: list[str] = Field(default_factory=list, description="Process ids or names in recommended order.")
    interview_needs: list[str] = Field(default_factory=list, description="Interviews or evidence needed by process.")
    next_actions: list[str] = Field(default_factory=list, description="Concrete cross-process next actions.")


class ProcessHandoffInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Process id receiving the handoff.")
    expected_result: str = Field(description="What the Process Macro Agent should produce.")
    reason: str = Field(description="Why this process should be handled now.")
    known_context: str = Field(default="", description="Minimal facts, source ids or blockers for the handoff.")


class CrossProcessIssueInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    title: str = Field(description="Short cross-process issue title.")
    reason: str = Field(description="Why this is a cross-process issue.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids when known.")
    owner: str = Field(default="Project Macro Agent", description="Responsible owner or scope.")


def _project_payload(project_id: str) -> dict:
    # G3: il project_id qui e' un argomento del tool deciso dall'LLM. Dentro un
    # agent run vincolato deve combaciare con lo scope autorizzato del thread.
    from backend.agents.scope_guard import assert_project_in_scope

    assert_project_in_scope(project_id)

    project = workspace_database.get_project(project_id)
    if project is None:
        raise ValueError(f"Progetto non trovato: {project_id}")

    sources = workspace_database.list_project_sources(project_id)
    decisions = workspace_database.list_project_decisions(project_id)
    processes = project.get("process_items") or []
    process_readiness = [
        {
            "process_id": process["id"],
            "name": process["name"],
            "stage": process["stage"],
            "status": process["status"],
            "owner": process["owner"],
            "readiness": process["readiness"],
            "bpmn_model_id": process["bpmn_model_id"],
        }
        for process in processes
    ]

    return {
        "project": project,
        "sources": sources,
        "decisions": decisions,
        "processes": processes,
        "process_readiness": process_readiness,
    }


@tool
def get_project_workspace_brief(project_id: str) -> str:
    """
    Provide the authorized project workspace snapshot for project-level synthesis and routing.
    
    Args:
        project_id (str): Untrusted project identifier used to select the project.
    
    Returns:
        str: Structured result containing project status and progress, sources, decisions,
            process counts, and process-readiness data.
    
    Raises:
        ValueError: If the project does not exist or is outside the authorized scope.
    
    This function is read-only and does not persist changes.
    """
    payload = _project_payload(project_id)
    project = payload["project"]

    return enterprise_tool_result(
        status="ok",
        action="get_project_workspace_brief",
        entity_type="project",
        entity_id=project_id,
        summary=f"{project['name']} - {project['status']} - {project['progress']}%",
        payload={
            "project": project,
            "source_count": len(payload["sources"]),
            "decision_count": len(payload["decisions"]),
            "process_count": len(payload["processes"]),
            "sources": payload["sources"],
            "decisions": payload["decisions"],
            "process_readiness": payload["process_readiness"],
        },
    )


@tool(args_schema=ProjectProcessRecordInput)
def create_project_process(
    project_id: str,
    name: str,
    stage: str = "AS-IS",
    owner: str = "Da assegnare",
    scope_note: str = "",
) -> str:
    """
    Register a process in the authorized project workspace without starting discovery or BPMN generation.
    
    The operation is idempotent by normalized process name: an existing matching process is
    returned instead of creating a duplicate. For a new process, it persists the process and
    its empty BPMN model. When provided, the stated perimeter is persisted as a project source
    linked to the process; otherwise, the result includes a warning.
    
    Args:
        project_id (str, untrusted): Identifier of the project in which to register the process.
        name (str, untrusted): Process name used for registration and duplicate detection.
        stage (str, untrusted): Process lifecycle stage.
        owner (str, untrusted): Initial process owner.
        scope_note (str, untrusted): Optional stated perimeter for the process.
    
    Returns:
        str: A serialized result indicating whether the process already existed or was created,
            including the process details, BPMN model identifier, and any warnings or follow-up
            actions.
    
    Raises:
        ValueError: If the project is outside the authorized scope or does not exist.
    """
    payload = _project_payload(project_id)
    wanted = " ".join(name.casefold().split())
    existing = next(
        (
            process
            for process in payload["processes"]
            if " ".join(str(process["name"]).casefold().split()) == wanted
        ),
        None,
    )
    if existing:
        return enterprise_tool_result(
            status="exists",
            action="create_project_process",
            entity_type="process",
            entity_id=existing["id"],
            summary=f"Processo gia registrato nel progetto: {existing['name']}",
            payload={"project_id": project_id, "process": existing},
            warnings=["Existing process returned instead of creating a duplicate."],
        )

    process = workspace_database.create_process(
        project_id=project_id,
        name=name,
        stage=stage,
        owner=owner,
    )

    warnings = []
    perimeter_source = None
    if scope_note.strip():
        perimeter_source = workspace_database.create_project_source(
            project_id=project_id,
            process_id=process["id"],
            name=f"Perimetro - {process['name']}",
            type="Perimetro",
            meta=scope_note.strip(),
        )
    else:
        warnings.append(
            "Process registered without a stated perimeter: nothing records where it "
            "starts and ends. Ask the consultant, or record it later as a source."
        )

    return enterprise_tool_result(
        status="created",
        action="create_project_process",
        entity_type="process",
        entity_id=process["id"],
        summary=f"Processo registrato nel progetto: {process['name']}",
        payload={
            "project_id": project_id,
            "process": process,
            "process_id": process["id"],
            "bpmn_model_id": process["bpmn_model_id"],
            "perimeter_source": perimeter_source,
        },
        warnings=warnings,
        next_actions=[
            {
                "owner": "Project Macro Agent",
                "action": "Registrare gli altri processi in scope, se il consulente ne ha altri.",
            },
            {
                "owner": "Process Macro Agent",
                "action": (
                    "Discovery AS-IS su questo processo, nella chat processo, "
                    "quando il consulente decide di partire."
                ),
            },
        ],
    )


@tool(args_schema=ProjectDelegationPayloadInput)
def prepare_project_delegation_payload(
    target_owner: str,
    user_request: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Prepare a structured handoff payload without executing or persisting delegated work.
    
    Args:
        target_owner (str): Untrusted input identifying the intended receiving owner or agent.
        user_request (str): Untrusted input containing the requested work.
        expected_result (str): Untrusted input describing the expected outcome.
        reason (str): Untrusted input explaining the delegation rationale.
        known_context (str): Untrusted input containing relevant context.
    
    Returns:
        str: A JSON-formatted delegation payload with status, routing, request,
            expected result, reason, and known context.
    """
    return "Project delegation payload\n" + json.dumps(
        {
            "status": "prepared",
            "action": "prepare_project_delegation_payload",
            "target_owner": target_owner,
            "user_request": user_request,
            "expected_result": expected_result,
            "reason": reason,
            "known_context": known_context,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def get_project_delivery_brief(project_id: str) -> str:
    """
    Builds a delivery-focused brief for an authorized project.
    
    The project must be within the authorized scope and must exist. This function
    only reads project context and does not modify or persist data.
    
    Args:
        project_id (str): Untrusted project identifier used to locate the project.
    
    Returns:
        str: Serialized project delivery context, including objective, phase, status,
            progress, next step, milestones, deliverables, open issues, and
            decisions.
    
    Raises:
        PermissionError: If the project is outside the authorized scope.
        ValueError: If the project does not exist.
    """
    payload = _project_payload(project_id)
    project = payload["project"]

    return enterprise_tool_result(
        status="ok",
        action="get_project_delivery_brief",
        entity_type="project_delivery",
        entity_id=project_id,
        summary=f"Delivery brief for {project['name']}",
        payload={
            "project_id": project_id,
            "client": project["client"],
            "name": project["name"],
            "objective": project.get("objective") or "",
            "phase": project["phase"],
            "status": project["status"],
            "progress": project["progress"],
            "next_step": project["next_step"],
            "milestones": project["milestones"],
            "deliverables": project["deliverables"],
            "open_issues": project["open_issues"],
            "decisions": payload["decisions"],
        },
    )


@tool(args_schema=ProjectStatusUpdateInput)
def prepare_project_status_update(
    project_id: str,
    summary: str,
    phase: str | None = None,
    status: str | None = None,
    progress: int | None = None,
    next_step: str | None = None,
    risks: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> str:
    """
    Purpose: prepare a project status update for user review without mutating the
    workspace database. Use for phase, status, progress, risks and next actions.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_project_status_update",
        entity_type="project_delivery_update",
        entity_id=project_id,
        summary=summary,
        payload={
            "project_id": project_id,
            "summary": summary,
            "suggested_changes": {
                "phase": phase,
                "status": status,
                "progress": progress,
                "next_step": next_step,
            },
            "risks": risks or [],
            "next_actions": next_actions or [],
        },
    )


@tool(args_schema=DeliverablePlanInput)
def prepare_deliverable_plan(
    project_id: str,
    objective: str,
    deliverables: list[str] | None = None,
    assumptions: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> str:
    """
    Purpose: prepare a structured deliverable plan for the current project without
    changing workspace records.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_deliverable_plan",
        entity_type="project_deliverable_plan",
        entity_id=project_id,
        summary=objective,
        payload={
            "project_id": project_id,
            "objective": objective,
            "deliverables": deliverables or [],
            "assumptions": assumptions or [],
            "next_actions": next_actions or [],
        },
    )


@tool(args_schema=ProjectItemInput)
def record_project_risk(
    project_id: str,
    title: str,
    reason: str,
    owner: str = "Da assegnare",
    severity: str = "medium",
) -> str:
    """
    Purpose: prepare one project-level risk item for state/UI handoff. This does
    not persist a database record yet.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_project_risk",
        entity_type="project_risk",
        entity_id=project_id,
        summary=title,
        payload={
            "project_id": project_id,
            "title": title,
            "reason": reason,
            "owner": owner,
            "severity": severity,
        },
    )


@tool(args_schema=ProjectItemInput)
def record_project_next_action(
    project_id: str,
    title: str,
    reason: str,
    owner: str = "Da assegnare",
    severity: str = "medium",
) -> str:
    """
    Purpose: prepare one project-level next action for state/UI handoff. Severity
    is accepted for schema reuse but is not required for action interpretation.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_project_next_action",
        entity_type="project_next_action",
        entity_id=project_id,
        summary=title,
        payload={
            "project_id": project_id,
            "title": title,
            "reason": reason,
            "owner": owner,
            "severity": severity,
        },
    )


@tool
def get_project_process_map(project_id: str) -> str:
    """
    Read all processes in the current project with stage, status, owner, readiness
    and BPMN model id. Use for multi-process coordination. This is read-only.
    """
    payload = _project_payload(project_id)

    return enterprise_tool_result(
        status="ok",
        action="get_project_process_map",
        entity_type="project_process_map",
        entity_id=project_id,
        summary=f"{len(payload['processes'])} processi nel progetto.",
        payload={
            "project_id": project_id,
            "processes": payload["processes"],
            "sources": payload["sources"],
            "decisions": payload["decisions"],
        },
    )


@tool
def get_process_readiness_matrix(project_id: str) -> str:
    """
    Read the readiness matrix for all project processes. Use to identify incomplete,
    blocked or ready processes before planning handoffs.
    """
    payload = _project_payload(project_id)
    matrix = sorted(payload["process_readiness"], key=lambda item: item["readiness"])

    return enterprise_tool_result(
        status="ok",
        action="get_process_readiness_matrix",
        entity_type="process_readiness_matrix",
        entity_id=project_id,
        summary=f"Readiness matrix for {len(matrix)} processi.",
        payload={"project_id": project_id, "matrix": matrix},
    )


@tool(args_schema=DependencyIdentificationInput)
def identify_cross_process_dependencies(
    project_id: str,
    reason: str,
    relationship_hints: list[str] | None = None,
) -> str:
    """
    Purpose: prepare cross-process dependency analysis using explicit hints and
    current process/source/decision context. The workspace has no dependency table
    yet, so inferred dependencies must be labeled as assumptions.
    """
    payload = _project_payload(project_id)
    warnings = []
    if not relationship_hints:
        warnings.append("No explicit dependency hints provided; treat dependencies as hypotheses.")

    return enterprise_tool_result(
        status="prepared",
        action="identify_cross_process_dependencies",
        entity_type="cross_process_dependencies",
        entity_id=project_id,
        summary=reason,
        payload={
            "project_id": project_id,
            "processes": payload["process_readiness"],
            "relationship_hints": relationship_hints or [],
            "decisions": payload["decisions"],
            "sources": payload["sources"],
        },
        warnings=warnings,
    )


@tool(args_schema=ProcessWorkplanInput)
def prepare_process_workplan(
    project_id: str,
    objective: str,
    focus_order: list[str] | None = None,
    interview_needs: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> str:
    """
    Purpose: prepare a multi-process workplan for the current project. Use when
    the user needs sequencing, interview planning or project-level process focus.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_process_workplan",
        entity_type="project_process_workplan",
        entity_id=project_id,
        summary=objective,
        payload={
            "project_id": project_id,
            "objective": objective,
            "focus_order": focus_order or [],
            "interview_needs": interview_needs or [],
            "next_actions": next_actions or [],
        },
    )


@tool(args_schema=ProcessHandoffInput)
def prepare_process_handoff(
    project_id: str,
    process_id: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Purpose: prepare a focused handoff from Project Process Coordination to the
    Process Macro Agent for one process.
    """
    process = workspace_database.get_process(process_id)
    if process is None or process["project_id"] != project_id:
        raise ValueError(f"Processo non trovato nel progetto corrente: {process_id}")

    return enterprise_tool_result(
        status="prepared",
        action="prepare_process_handoff",
        entity_type="process_handoff",
        entity_id=process_id,
        summary=expected_result,
        payload={
            "target_owner": "process_macro",
            "project_id": project_id,
            "process_id": process_id,
            "bpmn_model_id": process["bpmn_model_id"],
            "expected_result": expected_result,
            "reason": reason,
            "known_context": known_context,
        },
    )


@tool(args_schema=CrossProcessIssueInput)
def record_cross_process_issue(
    project_id: str,
    title: str,
    reason: str,
    affected_process_ids: list[str] | None = None,
    owner: str = "Project Macro Agent",
) -> str:
    """
    Purpose: prepare one cross-process issue for state/UI handoff. This does not
    persist a database record yet.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_cross_process_issue",
        entity_type="cross_process_issue",
        entity_id=project_id,
        summary=title,
        payload={
            "project_id": project_id,
            "title": title,
            "reason": reason,
            "affected_process_ids": affected_process_ids or [],
            "owner": owner,
        },
    )


PROJECT_TOOL_POLICY = """
Project macro tools.

The Project Macro Agent owns project-level orchestration, not every project
operation. It can read the project brief, register the processes in scope,
prepare handoff payloads, save project-scoped episodic evidence, prepare
enterprise graph extraction from evidence, and retrieve project-scoped GraphRAG
context for relation-heavy questions, gaps, inconsistencies, cross-process
impact and ROI.

The processes of a project are project records: creating one is workspace setup
and belongs here, with `create_project_process`. What happens *inside* a process
does not: delivery execution belongs to the Delivery subgraph, multi-process
orchestration to the Process Coordination subgraph, AS-IS/BPMN work to Process
or Canvas macro agents. Registering a process must not turn into discovery in
the same turn.

A project with no registered processes has no process readiness, no process
dependencies and no missing process knowledge. Do not infer any of it: at that
point the only work available here is agreeing the portfolio of processes in
scope.

Never describe buttons, menu items or screens as a way around a missing
capability. If the workspace cannot do something, say which capability is
missing.
""".strip()


project_tools = [
    get_project_workspace_brief,
    create_project_process,
    prepare_project_delegation_payload,
    manage_project_evidence,
    extract_project_graph_from_evidence,
    extract_playbook_from_episodes,
    retrieve_project_graph_context,
    retrieve_project_gap_context,
    retrieve_cross_process_impact_context,
]
