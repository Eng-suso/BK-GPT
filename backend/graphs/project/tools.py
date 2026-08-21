import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.toolsets.project_memory import (
    extract_project_graph_from_evidence,
    manage_project_evidence,
    retrieve_cross_process_impact_context,
    retrieve_project_gap_context,
    retrieve_project_graph_context,
)
from backend.toolsets.workspace import enterprise_tool_result


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
    Read the authoritative project workspace snapshot: project status, process list,
    sources, decisions, deliverables and open issues. Use before project-level synthesis
    or routing when project context is needed. This is read-only.
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


@tool(args_schema=ProjectDelegationPayloadInput)
def prepare_project_delegation_payload(
    target_owner: str,
    user_request: str,
    expected_result: str,
    reason: str,
    known_context: str = "",
) -> str:
    """
    Purpose: create a narrow structured handoff payload from Project Macro to a
    project subgraph, Process Macro or Canvas Macro. This does not execute the
    delegated work.
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
    Read project delivery context: phase, status, progress, next step, milestones,
    deliverables, open issues and open decisions. Use for delivery planning/status.
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
operation. It can read the project brief, prepare handoff payloads, save
project-scoped episodic evidence, prepare enterprise graph extraction from
evidence, and retrieve project-scoped GraphRAG context for relation-heavy
questions, gaps, inconsistencies, cross-process impact and ROI.
Delivery execution belongs to the Delivery subgraph. Multi-process orchestration
belongs to the Process Coordination subgraph. AS-IS/BPMN work belongs to Process
or Canvas macro agents.
""".strip()


project_tools = [
    get_project_workspace_brief,
    prepare_project_delegation_payload,
    manage_project_evidence,
    extract_project_graph_from_evidence,
    retrieve_project_graph_context,
    retrieve_project_gap_context,
    retrieve_cross_process_impact_context,
]
