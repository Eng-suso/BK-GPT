from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.graphs.process.tools import process_workspace_payload
from backend.toolsets.workspace import enterprise_tool_result


class DiscoveryPlanInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    objective: str = Field(description="Discovery objective for this process turn.")
    known_boundaries: list[str] = Field(default_factory=list, description="Known trigger, start, end or scope facts.")
    stakeholders_to_interview: list[str] = Field(default_factory=list, description="Stakeholders or roles to consult.")
    sources_to_collect: list[str] = Field(default_factory=list, description="Documents, systems, examples or observations needed.")
    questions: list[str] = Field(default_factory=list, description="Concrete discovery questions to ask next.")


class DiscoveryFactsInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    source_name: str = Field(description="Evidence source used to derive these facts.")
    confirmed_facts: list[str] = Field(default_factory=list, description="Facts explicitly supported by the source.")
    hypotheses: list[str] = Field(default_factory=list, description="Plausible but unconfirmed process hypotheses.")
    missing_knowledge: list[str] = Field(default_factory=list, description="Gaps discovered from this source.")
    official_vs_actual_notes: list[str] = Field(
        default_factory=list,
        description="Differences between formal process and observed actual work.",
    )


class DiscoveryReadinessInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    scope_boundaries_clear: bool = Field(description="Trigger, start, end and outcome are clear enough.")
    main_actors_identified: bool = Field(description="Main roles, teams or systems are identified.")
    activities_supported: bool = Field(description="Major activities are supported by evidence.")
    decisions_and_handoffs_known: bool = Field(description="Important decisions and handoffs are known.")
    exceptions_acknowledged: bool = Field(description="Major exceptions are represented or listed as gaps.")
    contradictions_documented: bool = Field(description="Known contradictions are documented.")
    remaining_gaps_explicit: bool = Field(description="Remaining gaps are visible and actionable.")
    blocker_notes: list[str] = Field(default_factory=list, description="Blocking gaps that prevent modeling.")


class FollowupQuestionsInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    target_stakeholder: str = Field(description="Stakeholder, role or source owner to ask next.")
    reason: str = Field(description="Why this stakeholder/source is the next best target.")
    questions: list[str] = Field(description="Concrete questions, preferably tied to gaps or contradictions.")


class ProcessGapInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    title: str = Field(description="Short gap title.")
    missing_information: str = Field(description="What information is missing.")
    affects: Literal[
        "scope",
        "actor",
        "activity",
        "decision",
        "handoff",
        "system",
        "data",
        "exception",
        "control",
        "timing",
        "canvas",
    ] = Field(description="Process area affected by this gap.")
    severity: Literal["blocking", "non_blocking", "optional_extension"] = Field(default="non_blocking")
    recommended_source: str = Field(default="", description="Best source or stakeholder to close the gap.")


@tool
def get_process_discovery_brief(process_id: str) -> str:
    """
    Read process context optimized for discovery: process metadata, project,
    linked sources, open decisions, missing review information and whether BPMN
    XML already exists. Use before planning discovery.
    """
    payload = process_workspace_payload(process_id)
    process = payload["process"]
    review = payload["review"]
    return enterprise_tool_result(
        status="ok",
        action="get_process_discovery_brief",
        entity_type="process_discovery_brief",
        entity_id=process_id,
        summary=f"Discovery brief for {process['name']}",
        payload={
            "process": process,
            "project": payload["project"],
            "sources": payload["sources"],
            "decisions": payload["decisions"],
            "missing_information": review.get("missing_information") if review else [],
            "has_saved_bpmn_xml": bool(payload["bpmn_model"] and payload["bpmn_model"]["has_xml"]),
        },
    )


@tool(args_schema=DiscoveryPlanInput)
def prepare_discovery_plan(
    process_id: str,
    objective: str,
    known_boundaries: list[str] | None = None,
    stakeholders_to_interview: list[str] | None = None,
    sources_to_collect: list[str] | None = None,
    questions: list[str] | None = None,
) -> str:
    """
    Prepare a discovery plan for one process. Use when the process is not ready
    for modeling and the next step is to collect or clarify knowledge.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_discovery_plan",
        entity_type="process_discovery_plan",
        entity_id=process_id,
        summary=objective,
        payload={
            "process_id": process_id,
            "known_boundaries": known_boundaries or [],
            "stakeholders_to_interview": stakeholders_to_interview or [],
            "sources_to_collect": sources_to_collect or [],
            "questions": questions or [],
        },
    )


@tool(args_schema=DiscoveryFactsInput)
def extract_discovery_facts(
    process_id: str,
    source_name: str,
    confirmed_facts: list[str] | None = None,
    hypotheses: list[str] | None = None,
    missing_knowledge: list[str] | None = None,
    official_vs_actual_notes: list[str] | None = None,
) -> str:
    """
    Structure discovery findings from a source. The LLM must separate confirmed
    facts, hypotheses, gaps and official-vs-actual differences.
    """
    return enterprise_tool_result(
        status="prepared",
        action="extract_discovery_facts",
        entity_type="process_discovery_facts",
        entity_id=process_id,
        summary=f"Discovery facts extracted from {source_name}",
        payload={
            "process_id": process_id,
            "source_name": source_name,
            "confirmed_facts": confirmed_facts or [],
            "hypotheses": hypotheses or [],
            "missing_knowledge": missing_knowledge or [],
            "official_vs_actual_notes": official_vs_actual_notes or [],
        },
    )


@tool(args_schema=DiscoveryReadinessInput)
def assess_discovery_readiness(
    process_id: str,
    scope_boundaries_clear: bool,
    main_actors_identified: bool,
    activities_supported: bool,
    decisions_and_handoffs_known: bool,
    exceptions_acknowledged: bool,
    contradictions_documented: bool,
    remaining_gaps_explicit: bool,
    blocker_notes: list[str] | None = None,
) -> str:
    """
    Assess whether discovery is ready to move into ProcessUnderstanding modeling.
    Use before routing from discovery/evidence to modeling.
    """
    checks = {
        "scope_boundaries_clear": scope_boundaries_clear,
        "main_actors_identified": main_actors_identified,
        "activities_supported": activities_supported,
        "decisions_and_handoffs_known": decisions_and_handoffs_known,
        "exceptions_acknowledged": exceptions_acknowledged,
        "contradictions_documented": contradictions_documented,
        "remaining_gaps_explicit": remaining_gaps_explicit,
    }
    passed = sum(1 for value in checks.values() if value)
    score = round((passed / len(checks)) * 10)
    blockers = blocker_notes or []
    status = "ready_for_modeling" if score >= 7 and not blockers else "discovery_required"

    return enterprise_tool_result(
        status=status,
        action="assess_discovery_readiness",
        entity_type="process_discovery_readiness",
        entity_id=process_id,
        summary=f"Discovery readiness score {score}/10.",
        payload={"process_id": process_id, "score": score, "checks": checks, "blockers": blockers},
        warnings=blockers,
    )


@tool(args_schema=FollowupQuestionsInput)
def prepare_followup_questions(
    process_id: str,
    target_stakeholder: str,
    reason: str,
    questions: list[str],
) -> str:
    """
    Prepare focused follow-up questions for the next interview, document owner or
    observation. Questions should close specific process gaps.
    """
    return enterprise_tool_result(
        status="prepared",
        action="prepare_followup_questions",
        entity_type="process_followup_questions",
        entity_id=process_id,
        summary=f"Follow-up questions for {target_stakeholder}",
        payload={
            "process_id": process_id,
            "target_stakeholder": target_stakeholder,
            "reason": reason,
            "questions": questions,
        },
    )


@tool(args_schema=ProcessGapInput)
def record_process_gap(
    process_id: str,
    title: str,
    missing_information: str,
    affects: str,
    severity: str = "non_blocking",
    recommended_source: str = "",
) -> str:
    """
    Prepare one process gap for state/UI handoff. This does not persist a gap
    table yet; save it as evidence or decision only when explicitly requested.
    """
    return enterprise_tool_result(
        status="prepared",
        action="record_process_gap",
        entity_type="process_gap",
        entity_id=process_id,
        summary=title,
        payload={
            "process_id": process_id,
            "title": title,
            "missing_information": missing_information,
            "affects": affects,
            "severity": severity,
            "recommended_source": recommended_source,
        },
    )


DISCOVERY_TOOL_POLICY = """
Process Discovery subagent tools.

The Discovery subagent owns process scope, boundaries, stakeholders, official
versus actual flow, missing knowledge and readiness to model. It does not create
BPMN XML and does not treat hypotheses as confirmed facts.
""".strip()


discovery_tools = [
    get_process_discovery_brief,
    prepare_discovery_plan,
    extract_discovery_facts,
    assess_discovery_readiness,
    prepare_followup_questions,
    record_process_gap,
]
