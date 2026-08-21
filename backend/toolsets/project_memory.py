from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.memory.episodic import episodic_store
from backend.memory.knowledge_graph import knowledge_graph_store
from backend.memory.knowledge_graph.models import (
    KnowledgeGraphContradiction,
    KnowledgeGraphEvidence,
    KnowledgeGraphGap,
    KnowledgeGraphImpact,
    KnowledgeGraphQuery,
    KnowledgeGraphRelationship,
)
from backend.memory.semantic import semantic_store
from backend.toolsets.workspace import enterprise_tool_result


class SaveProjectEpisodeInput(BaseModel):
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    episode_type: str = Field(description="Event type: note, call, decision, interview, workshop, feedback, or observation.")
    title: str = Field(description="Short source-backed event title.")
    raw_content: str = Field(description="Original notes/transcript/source text to store as raw source custody.")
    summary: str = Field(default="", description="Concise extracted summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from raw content.")
    participants: list[str] = Field(default_factory=list, description="People, roles or teams involved.")
    process_ids: list[str] = Field(default_factory=list, description="Related process ids inside the project.")
    entities: list[str] = Field(default_factory=list, description="Named project entities mentioned in the evidence.")
    relationships: list["ProjectGraphRelationship"] = Field(
        default_factory=list,
        description="Enterprise graph relationships extracted from the evidence.",
    )
    gaps: list["ProjectGraphGap"] = Field(default_factory=list, description="Missing data or evidence gaps.")
    inconsistencies: list["ProjectGraphInconsistency"] = Field(
        default_factory=list,
        description="Contradictions or incoherent stories across evidence.",
    )
    roi_impacts: list["ProjectROIImpact"] = Field(
        default_factory=list,
        description="Potential ROI, cost, revenue, risk or efficiency impacts.",
    )
    tags: list[str] = Field(default_factory=list, description="Additional retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class SaveProjectInterviewInput(BaseModel):
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    title: str = Field(description="Short interview title.")
    raw_content: str = Field(description="Original interview transcript or notes.")
    summary: str = Field(default="", description="Concise extracted interview summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from the interview.")
    participants: list[str] = Field(default_factory=list, description="Interview participants, roles or teams.")
    process_ids: list[str] = Field(default_factory=list, description="Related process ids inside the project.")
    entities: list[str] = Field(default_factory=list, description="Named project entities mentioned in the interview.")
    relationships: list["ProjectGraphRelationship"] = Field(
        default_factory=list,
        description="Enterprise graph relationships extracted from the interview.",
    )
    gaps: list["ProjectGraphGap"] = Field(default_factory=list, description="Missing data or evidence gaps.")
    inconsistencies: list["ProjectGraphInconsistency"] = Field(
        default_factory=list,
        description="Contradictions or incoherent stories across evidence.",
    )
    roi_impacts: list["ProjectROIImpact"] = Field(
        default_factory=list,
        description="Potential ROI, cost, revenue, risk or efficiency impacts.",
    )
    tags: list[str] = Field(default_factory=list, description="Additional retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class RetrieveProjectEvidenceInput(BaseModel):
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    query: str = Field(description="Evidence retrieval question.")
    episode_type: str | None = Field(default=None, description="Optional episode type filter, such as interview or decision.")
    process_id: str | None = Field(default=None, description="Optional related process id.")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum local evidence matches.")
    reason: str = Field(description="Why this evidence retrieval is needed for the current turn.")


class ManageProjectEvidenceInput(BaseModel):
    operation: str = Field(
        description=(
            "Project evidence lifecycle operation. Use list/search/inspect to retrieve project evidence; "
            "use save_interview or save_episode to store source-backed project evidence with optional KG extraction; "
            "use update_metadata for labels; use archive for normal removal from active retrieval; "
            "use restore to reactivate; use delete only after explicit destructive confirmation."
        )
    )
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    episode_id: str | None = Field(default=None, description="Target episode_id for inspect, update_metadata, archive, restore, or delete.")
    source_id: str | None = Field(default=None, description="Optional source_id for inspect when episode_id is unknown.")
    query: str = Field(default="", description="Search/list query. Leave empty to list recent project evidence.")
    episode_type: str | None = Field(default=None, description="Filter or save type: interview, call, note, decision, workshop, feedback, observation.")
    title: str = Field(default="", description="Evidence title for save/update.")
    raw_content: str = Field(default="", description="Original notes/transcript/source text for save operations.")
    summary: str = Field(default="", description="Concise extracted summary for save/update.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights for save/update.")
    participants: list[str] = Field(default_factory=list, description="People, roles or teams involved.")
    process_ids: list[str] = Field(default_factory=list, description="Related process ids inside the project.")
    entities: list[str] = Field(default_factory=list, description="Named project entities mentioned in the evidence.")
    relationships: list["ProjectGraphRelationship"] = Field(default_factory=list, description="Enterprise graph relationships extracted from evidence.")
    gaps: list["ProjectGraphGap"] = Field(default_factory=list, description="Missing data or evidence gaps.")
    inconsistencies: list["ProjectGraphInconsistency"] = Field(default_factory=list, description="Contradictions or incoherent stories across evidence.")
    roi_impacts: list["ProjectROIImpact"] = Field(default_factory=list, description="ROI, cost, risk, quality, time or efficiency impacts.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags for save/update.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")
    status: str = Field(default="active", description="For list: active, archived, or any.")
    reason: str = Field(default="", description="Why this lifecycle action is being taken, especially archive/delete.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum evidence records to return.")
    include_source_text: bool = Field(default=False, description="For inspect: include raw source text when needed.")
    confirm_destructive_action: bool = Field(default=False, description="Required for hard delete. Prefer archive for ordinary removal.")
    delete_raw_source: bool = Field(default=False, description="Also delete local raw source file during confirmed hard delete.")


class RetrieveProjectGraphContextInput(BaseModel):
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    query: str = Field(description="Relation-heavy project question to answer.")
    relation_focus: str = Field(
        description=(
            "Relation type to inspect, such as process-to-process, process-to-source, "
            "decision-to-risk, interview-to-process, stakeholder-to-process, "
            "deliverable-to-process, or insight-to-evidence."
        )
    )
    reason: str = Field(description="Why graph-style project retrieval is needed now.")
    entities: list[str] = Field(default_factory=list, description="Named entities to anchor retrieval.")
    process_ids: list[str] = Field(default_factory=list, description="Process ids to anchor retrieval.")
    include_workspace_snapshot: bool = Field(default=True, description="Include current project workspace grounding.")
    include_evidence: bool = Field(default=True, description="Include project-scoped episodic evidence.")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum episodic matches.")


class ProjectGraphRelationship(BaseModel):
    source: str = Field(description="Source node, such as process:Acquisti, stakeholder:CFO, source:Intervista CFO.")
    relation: str = Field(
        description="Relationship label, such as DEPENDS_ON, SUPPORTS, BLOCKS, USES_INPUT, PRODUCES_OUTPUT, OWNS, AFFECTS_ROI."
    )
    target: str = Field(description="Target node.")
    evidence: str = Field(description="Short evidence statement supporting the relationship.")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="Confidence in this relationship.")
    confirmed: bool = Field(default=False, description="Whether this relationship has been validated.")


class ProjectGraphGap(BaseModel):
    title: str = Field(description="Short gap title.")
    missing_information: str = Field(description="What information is missing.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids when known.")
    required_evidence: str = Field(default="", description="Evidence needed to close the gap.")
    severity: str = Field(default="medium", description="low, medium, high, or critical.")


class ProjectGraphInconsistency(BaseModel):
    title: str = Field(description="Short inconsistency title.")
    conflicting_claims: list[str] = Field(description="Claims that do not align.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids when known.")
    resolution_question: str = Field(description="Question needed to resolve the inconsistency.")
    severity: str = Field(default="medium", description="low, medium, high, or critical.")


class ProjectROIImpact(BaseModel):
    title: str = Field(description="Short ROI impact title.")
    impact_area: str = Field(description="cost, revenue, working_capital, risk, quality, time, compliance, or efficiency.")
    affected_process_ids: list[str] = Field(default_factory=list, description="Affected process ids when known.")
    mechanism: str = Field(description="How the process issue or dependency affects ROI.")
    evidence: str = Field(default="", description="Evidence supporting this impact.")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="Confidence in the ROI impact.")


class ExtractProjectGraphInput(BaseModel):
    project_id: str = Field(description="Current project id from the active Project Chat scope.")
    raw_content: str = Field(description="Interview, notes, source text, data notes or evidence to structure.")
    extraction_focus: list[str] = Field(
        default_factory=list,
        description="Focus areas, such as process_dependencies, missing_data, inconsistencies, roi_impacts, process_elements.",
    )
    process_ids: list[str] = Field(default_factory=list, description="Known related process ids.")
    entities: list[str] = Field(default_factory=list, description="Entities identified by the agent.")
    relationships: list[ProjectGraphRelationship] = Field(default_factory=list, description="Candidate relationships.")
    gaps: list[ProjectGraphGap] = Field(default_factory=list, description="Candidate evidence gaps.")
    inconsistencies: list[ProjectGraphInconsistency] = Field(default_factory=list, description="Candidate inconsistencies.")
    roi_impacts: list[ProjectROIImpact] = Field(default_factory=list, description="Candidate ROI impacts.")
    questions_to_validate: list[str] = Field(default_factory=list, description="Questions needed to validate the extraction.")
    reason: str = Field(description="Why this extraction is needed.")


def _require_project(project_id: str) -> dict:
    project = workspace_database.get_project(project_id)
    if project is None:
        raise ValueError(f"Progetto non trovato: {project_id}")
    return project


def _validated_process_ids(project_id: str, process_ids: list[str] | None) -> list[str]:
    if not process_ids:
        return []

    known_processes = {
        process["id"]
        for process in workspace_database.list_project_processes(project_id)
    }
    cleaned = []

    for process_id in process_ids:
        normalized = str(process_id or "").strip()
        if normalized and normalized in known_processes and normalized not in cleaned:
            cleaned.append(normalized)

    return cleaned


def _project_episode_tags(
    *,
    project_id: str,
    process_ids: list[str],
    tags: list[str] | None,
) -> list[str]:
    normalized_tags = [f"project:{project_id}"]

    for process_id in process_ids:
        normalized_tags.append(f"process:{process_id}")

    for tag in tags or []:
        normalized = " ".join(str(tag or "").split())
        if normalized and normalized not in normalized_tags:
            normalized_tags.append(normalized)

    return normalized_tags


def _clean_text_list(values: list[str] | None) -> list[str]:
    cleaned = []

    for value in values or []:
        item = " ".join(str(value or "").split())
        if item and item not in cleaned:
            cleaned.append(item)

    return cleaned


def _graph_index_lines(
    *,
    project_id: str,
    process_ids: list[str],
    entities: list[str] | None,
    relationships: list[ProjectGraphRelationship] | None,
    gaps: list[ProjectGraphGap] | None,
    inconsistencies: list[ProjectGraphInconsistency] | None,
    roi_impacts: list[ProjectROIImpact] | None,
) -> list[str]:
    lines = [
        f"graph_scope: project",
        f"project_id: {project_id}",
    ]

    if process_ids:
        lines.append(f"process_ids: {', '.join(process_ids)}")

    entity_values = _clean_text_list(entities)
    if entity_values:
        lines.append(f"entities: {', '.join(entity_values)}")

    for relationship in relationships or []:
        lines.append(
            "relationship: "
            f"{relationship.source} {relationship.relation} {relationship.target} | "
            f"confirmed={str(relationship.confirmed).lower()} | "
            f"confidence={relationship.confidence} | "
            f"evidence={relationship.evidence}"
        )

    for gap in gaps or []:
        affected = ", ".join(gap.affected_process_ids) or "unknown"
        lines.append(
            "gap: "
            f"{gap.title} | affected_process_ids={affected} | "
            f"severity={gap.severity} | missing={gap.missing_information} | "
            f"required_evidence={gap.required_evidence or 'unspecified'}"
        )

    for inconsistency in inconsistencies or []:
        affected = ", ".join(inconsistency.affected_process_ids) or "unknown"
        claims = " || ".join(inconsistency.conflicting_claims)
        lines.append(
            "inconsistency: "
            f"{inconsistency.title} | affected_process_ids={affected} | "
            f"severity={inconsistency.severity} | claims={claims} | "
            f"resolution_question={inconsistency.resolution_question}"
        )

    for roi_impact in roi_impacts or []:
        affected = ", ".join(roi_impact.affected_process_ids) or "unknown"
        lines.append(
            "roi_impact: "
            f"{roi_impact.title} | area={roi_impact.impact_area} | "
            f"affected_process_ids={affected} | confidence={roi_impact.confidence} | "
            f"mechanism={roi_impact.mechanism} | evidence={roi_impact.evidence or 'unspecified'}"
        )

    return lines


def _graph_tags(
    *,
    entities: list[str] | None,
    relationships: list[ProjectGraphRelationship] | None,
    gaps: list[ProjectGraphGap] | None,
    inconsistencies: list[ProjectGraphInconsistency] | None,
    roi_impacts: list[ProjectROIImpact] | None,
) -> list[str]:
    tags = []

    for entity in _clean_text_list(entities):
        tags.append(f"entity:{entity}")

    if relationships:
        tags.append("graph:relationships")
        for relationship in relationships:
            relation_tag = f"relation:{relationship.relation}"
            if relation_tag not in tags:
                tags.append(relation_tag)

    if gaps:
        tags.append("graph:gaps")
    if inconsistencies:
        tags.append("graph:inconsistencies")
    if roi_impacts:
        tags.append("graph:roi")

    return tags


def _knowledge_graph_evidence_payload(
    *,
    project_id: str,
    scope: str,
    title: str,
    raw_content: str,
    reason: str,
    process_ids: list[str],
    entities: list[str] | None,
    relationships: list[ProjectGraphRelationship] | None,
    gaps: list[ProjectGraphGap] | None,
    inconsistencies: list[ProjectGraphInconsistency] | None,
    roi_impacts: list[ProjectROIImpact] | None,
    source_refs: list[str] | None = None,
) -> KnowledgeGraphEvidence:
    return KnowledgeGraphEvidence(
        project_id=project_id,
        scope=scope,
        source_title=title,
        raw_content=raw_content,
        reason=reason,
        process_ids=process_ids,
        entities=_clean_text_list(entities),
        relationships=[
            KnowledgeGraphRelationship(
                source=item.source,
                relation=item.relation,
                target=item.target,
                evidence=item.evidence,
                confidence=item.confidence,
                confirmed=item.confirmed,
            )
            for item in relationships or []
        ],
        gaps=[
            KnowledgeGraphGap(
                title=item.title,
                missing_information=item.missing_information,
                affected_process_ids=item.affected_process_ids,
                required_evidence=item.required_evidence,
                severity=item.severity,
            )
            for item in gaps or []
        ],
        contradictions=[
            KnowledgeGraphContradiction(
                title=item.title,
                conflicting_claims=item.conflicting_claims,
                affected_process_ids=item.affected_process_ids,
                resolution_question=item.resolution_question,
                severity=item.severity,
            )
            for item in inconsistencies or []
        ],
        impacts=[
            KnowledgeGraphImpact(
                title=item.title,
                impact_area=item.impact_area,
                affected_process_ids=item.affected_process_ids,
                mechanism=item.mechanism,
                evidence=item.evidence,
                confidence=item.confidence,
            )
            for item in roi_impacts or []
        ],
        source_refs=source_refs or [],
    )


def _project_workspace_graph_grounding(project_id: str) -> dict:
    project = _require_project(project_id)
    processes = workspace_database.list_project_processes(project_id)
    sources = workspace_database.list_project_sources(project_id)
    decisions = workspace_database.list_project_decisions(project_id)

    return {
        "project": project,
        "processes": processes,
        "sources": sources,
        "decisions": decisions,
    }


@tool(args_schema=SaveProjectEpisodeInput)
def save_project_episode(
    project_id: str,
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list[ProjectGraphRelationship] | None = None,
    gaps: list[ProjectGraphGap] | None = None,
    inconsistencies: list[ProjectGraphInconsistency] | None = None,
    roi_impacts: list[ProjectROIImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save a project-scoped episodic memory with raw source custody.
    Use when the Project Chat receives real project evidence such as notes, calls,
    workshop output, decisions, observations, feedback or interview-like material.
    The agent decides when evidence should be saved; this tool does not run automatically.
    """
    return _save_project_episode_payload(
        action="save_project_episode",
        entity_type="project_episode",
        project_id=project_id,
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights,
        participants=participants,
        process_ids=process_ids,
        entities=entities,
        relationships=relationships,
        gaps=gaps,
        inconsistencies=inconsistencies,
        roi_impacts=roi_impacts,
        tags=tags,
        occurred_at=occurred_at,
    )


def _save_project_episode_payload(
    *,
    action: str,
    entity_type: str,
    project_id: str,
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list[ProjectGraphRelationship] | None = None,
    gaps: list[ProjectGraphGap] | None = None,
    inconsistencies: list[ProjectGraphInconsistency] | None = None,
    roi_impacts: list[ProjectROIImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    project = _require_project(project_id)
    valid_process_ids = _validated_process_ids(project_id, process_ids)
    valid_process_set = set(valid_process_ids)
    valid_gaps = [
        gap.model_copy(
            update={
                "affected_process_ids": [
                    process_id for process_id in gap.affected_process_ids if process_id in valid_process_set
                ]
            }
        )
        for gap in gaps or []
    ]
    valid_inconsistencies = [
        inconsistency.model_copy(
            update={
                "affected_process_ids": [
                    process_id
                    for process_id in inconsistency.affected_process_ids
                    if process_id in valid_process_set
                ]
            }
        )
        for inconsistency in inconsistencies or []
    ]
    valid_roi_impacts = [
        roi_impact.model_copy(
            update={
                "affected_process_ids": [
                    process_id
                    for process_id in roi_impact.affected_process_ids
                    if process_id in valid_process_set
                ]
            }
        )
        for roi_impact in roi_impacts or []
    ]
    graph_lines = _graph_index_lines(
        project_id=project_id,
        process_ids=valid_process_ids,
        entities=entities,
        relationships=relationships,
        gaps=valid_gaps,
        inconsistencies=valid_inconsistencies,
        roi_impacts=valid_roi_impacts,
    )
    indexed_insights = [*(insights or [])]
    if len(graph_lines) > 2:
        indexed_insights.append("PROJECT_GRAPH_INDEX\n" + "\n".join(graph_lines))

    kg_index_result = None
    if relationships or valid_gaps or valid_inconsistencies or valid_roi_impacts or entities:
        kg_index_result = knowledge_graph_store.index_evidence_graph(
            _knowledge_graph_evidence_payload(
                project_id=project_id,
                scope="project",
                title=title,
                raw_content=raw_content,
                reason=f"{action}: {summary or title}",
                process_ids=valid_process_ids,
                entities=entities,
                relationships=relationships,
                gaps=valid_gaps,
                inconsistencies=valid_inconsistencies,
                roi_impacts=valid_roi_impacts,
            )
        )

    result = episodic_store.save_episode_memory(
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=indexed_insights,
        participants=participants or [],
        project=project_id,
        tags=_project_episode_tags(
            project_id=project_id,
            process_ids=valid_process_ids,
            tags=[*(tags or []), *_graph_tags(
                entities=entities,
                relationships=relationships,
                gaps=valid_gaps,
                inconsistencies=valid_inconsistencies,
                roi_impacts=valid_roi_impacts,
            )],
        ),
        occurred_at=occurred_at,
    )

    return enterprise_tool_result(
        status="saved",
        action=action,
        entity_type=entity_type,
        entity_id=project_id,
        summary=f"Episodio salvato per {project['name']}: {title}",
        payload={
            "project_id": project_id,
            "project_name": project["name"],
            "episode_type": episode_type,
            "title": title,
            "process_ids": valid_process_ids,
            "entities": _clean_text_list(entities),
            "relationships": [item.model_dump() for item in relationships or []],
            "gaps": [item.model_dump() for item in valid_gaps],
            "inconsistencies": [item.model_dump() for item in valid_inconsistencies],
            "roi_impacts": [item.model_dump() for item in valid_roi_impacts],
            "knowledge_graph_index": kg_index_result,
            "memory_result": result,
        },
    )


@tool(args_schema=SaveProjectInterviewInput)
def save_project_interview(
    project_id: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list[ProjectGraphRelationship] | None = None,
    gaps: list[ProjectGraphGap] | None = None,
    inconsistencies: list[ProjectGraphInconsistency] | None = None,
    roi_impacts: list[ProjectROIImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save a project-scoped interview as episodic memory with raw transcript custody.
    Use when the Project Chat receives an interview transcript, interview notes, or
    a user explicitly says the content is an interview for the current project.
    The agent decides when to call this tool; it is not deterministic middleware.
    """
    return _save_project_episode_payload(
        action="save_project_interview",
        entity_type="project_interview",
        project_id=project_id,
        episode_type="interview",
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights or [],
        participants=participants or [],
        process_ids=process_ids or [],
        entities=entities or [],
        relationships=relationships or [],
        gaps=gaps or [],
        inconsistencies=inconsistencies or [],
        roi_impacts=roi_impacts or [],
        tags=["interview", *(tags or [])],
        occurred_at=occurred_at,
    )


def _project_evidence_or_scope_error(
    *,
    project_id: str,
    episode_id: str | None = None,
    source_id: str | None = None,
    include_source_text: bool = False,
) -> tuple[dict | None, str | None]:
    evidence = episodic_store.get_episode_memory(
        episode_id=episode_id,
        source_id=source_id,
        include_source_text=include_source_text,
    )
    if evidence is None:
        return None, "Project evidence not found."
    if evidence.get("project") != project_id:
        return evidence, f"Evidence {evidence.get('episode_id')} does not belong to project {project_id}."
    return evidence, None


@tool(args_schema=ManageProjectEvidenceInput)
def manage_project_evidence(
    operation: str,
    project_id: str,
    episode_id: str | None = None,
    source_id: str | None = None,
    query: str = "",
    episode_type: str | None = None,
    title: str = "",
    raw_content: str = "",
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list[ProjectGraphRelationship] | None = None,
    gaps: list[ProjectGraphGap] | None = None,
    inconsistencies: list[ProjectGraphInconsistency] | None = None,
    roi_impacts: list[ProjectROIImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
    status: str = "active",
    reason: str = "",
    limit: int = 10,
    include_source_text: bool = False,
    confirm_destructive_action: bool = False,
    delete_raw_source: bool = False,
) -> str:
    """
    Manage project-scoped evidence through one lifecycle facade. Use this instead
    of separate CRUD-style tools when the Project Agent needs to list, inspect,
    save, update, archive, restore or explicitly delete interviews/episodes.
    Saves can include graph relationships, gaps, inconsistencies and ROI impacts;
    the existing project KG indexing path is preserved.
    """
    project = _require_project(project_id)
    normalized_operation = operation.strip().lower()
    normalized_status = status if status in {"active", "archived", "any"} else "active"

    if normalized_operation in {"list", "search"}:
        evidence = episodic_store.list_episode_memory(
            project=project_id,
            episode_type=episode_type,
            query=query,
            status=normalized_status,
            limit=limit,
        )
        return enterprise_tool_result(
            status="ok",
            action="manage_project_evidence",
            entity_type="project_evidence_collection",
            entity_id=project_id,
            summary=f"Project evidence {normalized_operation} for {project['name']}: {len(evidence)} record.",
            payload={
                "operation": normalized_operation,
                "project_id": project_id,
                "query": query,
                "episode_type": episode_type,
                "status": normalized_status,
                "evidence": evidence,
            },
        )

    if normalized_operation == "inspect":
        evidence, error = _project_evidence_or_scope_error(
            project_id=project_id,
            episode_id=episode_id,
            source_id=source_id,
            include_source_text=include_source_text,
        )
        return enterprise_tool_result(
            status="blocked" if error else "ok",
            action="manage_project_evidence",
            entity_type="project_evidence",
            entity_id=episode_id,
            summary=error or "Project evidence inspected.",
            payload={"operation": normalized_operation, "evidence": evidence},
        )

    if normalized_operation in {"save_interview", "save_episode"}:
        if not raw_content.strip():
            return enterprise_tool_result(
                status="blocked",
                action="manage_project_evidence",
                entity_type="project_evidence",
                entity_id=project_id,
                summary="Cannot save project evidence without raw_content.",
                payload={"operation": normalized_operation, "project_id": project_id},
            )
        return _save_project_episode_payload(
            action="manage_project_evidence",
            entity_type="project_interview" if normalized_operation == "save_interview" else "project_episode",
            project_id=project_id,
            episode_type="interview" if normalized_operation == "save_interview" else (episode_type or "note"),
            title=title,
            raw_content=raw_content,
            summary=summary,
            insights=insights or [],
            participants=participants or [],
            process_ids=process_ids or [],
            entities=entities or [],
            relationships=relationships or [],
            gaps=gaps or [],
            inconsistencies=inconsistencies or [],
            roi_impacts=roi_impacts or [],
            tags=["interview", *(tags or [])] if normalized_operation == "save_interview" else (tags or []),
            occurred_at=occurred_at,
        )

    if normalized_operation == "update_metadata":
        evidence, error = _project_evidence_or_scope_error(project_id=project_id, episode_id=episode_id)
        if error:
            return enterprise_tool_result(
                status="blocked",
                action="manage_project_evidence",
                entity_type="project_evidence",
                entity_id=episode_id,
                summary=error,
                payload={"operation": normalized_operation, "evidence": evidence},
            )
        result = episodic_store.update_episode_metadata(
            episode_id=episode_id or "",
            title=title if title else None,
            summary=summary if summary else None,
            insights=insights if insights else None,
            participants=participants if participants else None,
            project=project_id,
            tags=_project_episode_tags(
                project_id=project_id,
                process_ids=_validated_process_ids(project_id, process_ids),
                tags=tags or [],
            ) if tags or process_ids else None,
            occurred_at=occurred_at,
        )
        return enterprise_tool_result(
            status=result["status"],
            action="manage_project_evidence",
            entity_type="project_evidence",
            entity_id=episode_id,
            summary=result["message"],
            payload={"operation": normalized_operation, "result": result},
        )

    if normalized_operation in {"archive", "restore", "delete"}:
        evidence, error = _project_evidence_or_scope_error(project_id=project_id, episode_id=episode_id)
        if error:
            return enterprise_tool_result(
                status="blocked",
                action="manage_project_evidence",
                entity_type="project_evidence",
                entity_id=episode_id,
                summary=error,
                payload={"operation": normalized_operation, "evidence": evidence},
            )
        if normalized_operation == "archive":
            result = episodic_store.archive_episode_memory(episode_id=episode_id or "", reason=reason)
        elif normalized_operation == "restore":
            result = episodic_store.restore_episode_memory(episode_id=episode_id or "")
        else:
            result = episodic_store.delete_episode_memory(
                episode_id=episode_id or "",
                confirm_destructive_action=confirm_destructive_action,
                delete_raw_source=delete_raw_source,
            )
        return enterprise_tool_result(
            status=result["status"],
            action="manage_project_evidence",
            entity_type="project_evidence",
            entity_id=episode_id,
            summary=result["message"],
            payload={
                "operation": normalized_operation,
                "result": result,
                "knowledge_graph_note": (
                    "Archived evidence is excluded from active episodic retrieval. "
                    "Existing LlamaIndex KG records remain available until a KG lifecycle operation is added."
                ),
            },
        )

    return enterprise_tool_result(
        status="blocked",
        action="manage_project_evidence",
        entity_type="project_evidence",
        entity_id=project_id,
        summary=f"Unsupported operation: {operation}.",
        payload={"operation": normalized_operation},
    )


@tool(args_schema=RetrieveProjectEvidenceInput)
def retrieve_project_evidence_context(
    project_id: str,
    query: str,
    reason: str,
    episode_type: str | None = None,
    process_id: str | None = None,
    limit: int = 5,
) -> str:
    """
    Retrieve project-scoped episodic evidence from local source custody and Mem0
    indexing. Use before answering project questions that depend on interviews,
    calls, notes, decisions, source-backed observations or evidence provenance.
    """
    project = _require_project(project_id)
    evidence_query = query
    if process_id:
        evidence_query = f"{query} process:{process_id}"

    evidence = episodic_store.search_episode_memory(
        query=evidence_query,
        episode_type=episode_type,
        project=project_id,
        limit=limit,
    )

    return enterprise_tool_result(
        status="ok",
        action="retrieve_project_evidence_context",
        entity_type="project_evidence_context",
        entity_id=project_id,
        summary=f"Evidence retrieval for {project['name']}: {reason}",
        payload={
            "project_id": project_id,
            "project_name": project["name"],
            "query": query,
            "episode_type": episode_type,
            "process_id": process_id,
            "reason": reason,
            "evidence": evidence,
        },
    )


@tool(args_schema=RetrieveProjectGraphContextInput)
def retrieve_project_graph_context(
    project_id: str,
    query: str,
    relation_focus: str,
    reason: str,
    entities: list[str] | None = None,
    process_ids: list[str] | None = None,
    include_workspace_snapshot: bool = True,
    include_evidence: bool = True,
    limit: int = 5,
) -> str:
    """
    Retrieve project-scoped GraphRAG context using Mem0 relational/entity memory,
    project-scoped episodic evidence and optional workspace DB grounding.
    Use for relation-heavy Project Chat questions: process dependencies, evidence
    links, stakeholder/process coverage, decision impacts, deliverable dependencies
    and insight-to-source provenance. Workspace DB remains the operational source
    of truth.
    """
    project = _require_project(project_id)
    valid_process_ids = _validated_process_ids(project_id, process_ids)
    entity_terms = [str(entity).strip() for entity in entities or [] if str(entity).strip()]
    process_terms = [f"process:{process_id}" for process_id in valid_process_ids]
    relational_query = "\n".join(
        [
            "scope: project_graph",
            f"project_id: {project_id}",
            f"project_name: {project['name']}",
            f"relation_focus: {relation_focus}",
            f"entities: {', '.join(entity_terms) or 'none'}",
            f"process_ids: {', '.join(valid_process_ids) or 'none'}",
            f"query: {query}",
        ]
    )
    mem0_result = semantic_store.search_consultant_memory(
        query=relational_query,
        category=None,
    )
    evidence_result = (
        episodic_store.search_episode_memory(
            query=" ".join([query, *entity_terms, *process_terms]).strip(),
            project=project_id,
            limit=limit,
        )
        if include_evidence
        else "Project evidence not requested."
    )
    workspace_grounding = (
        _project_workspace_graph_grounding(project_id)
        if include_workspace_snapshot
        else {"status": "workspace_snapshot_not_requested"}
    )
    knowledge_graph_context = knowledge_graph_store.retrieve_graph_context(
        KnowledgeGraphQuery(
            project_id=project_id,
            query=query,
            relation_focus=relation_focus,
            reason=reason,
            entities=entity_terms,
            process_ids=valid_process_ids,
            limit=limit,
        )
    )

    return enterprise_tool_result(
        status="ok",
        action="retrieve_project_graph_context",
        entity_type="project_graph_context",
        entity_id=project_id,
        summary=f"Project GraphRAG retrieval for {project['name']}: {relation_focus}",
        payload={
            "project_id": project_id,
            "project_name": project["name"],
            "query": query,
            "relation_focus": relation_focus,
            "reason": reason,
            "entities": entity_terms,
            "process_ids": valid_process_ids,
            "enterprise_knowledge_graph": knowledge_graph_context.model_dump(mode="json"),
            "mem0_relational_memory": mem0_result,
            "project_evidence": evidence_result,
            "workspace_grounding": workspace_grounding,
            "caveat": (
                "Use Mem0/project evidence as relational retrieval context. "
                "Use workspace DB records as authoritative operational state."
            ),
        },
    )


@tool(args_schema=ExtractProjectGraphInput)
def extract_project_graph_from_evidence(
    project_id: str,
    raw_content: str,
    reason: str,
    extraction_focus: list[str] | None = None,
    process_ids: list[str] | None = None,
    entities: list[str] | None = None,
    relationships: list[ProjectGraphRelationship] | None = None,
    gaps: list[ProjectGraphGap] | None = None,
    inconsistencies: list[ProjectGraphInconsistency] | None = None,
    roi_impacts: list[ProjectROIImpact] | None = None,
    questions_to_validate: list[str] | None = None,
) -> str:
    """
    Prepare an enterprise GraphRAG extraction from project evidence. The LLM
    supplies candidate relationships, gaps, inconsistencies and ROI impacts based
    on the raw content; this tool validates project/process scope and returns a
    structured review. It does not save memory automatically.
    """
    project = _require_project(project_id)
    valid_process_ids = _validated_process_ids(project_id, process_ids)
    valid_process_set = set(valid_process_ids)
    scoped_gaps = [
        gap.model_copy(
            update={
                "affected_process_ids": [
                    process_id for process_id in gap.affected_process_ids if process_id in valid_process_set
                ]
            }
        )
        for gap in gaps or []
    ]
    scoped_inconsistencies = [
        inconsistency.model_copy(
            update={
                "affected_process_ids": [
                    process_id
                    for process_id in inconsistency.affected_process_ids
                    if process_id in valid_process_set
                ]
            }
        )
        for inconsistency in inconsistencies or []
    ]
    scoped_roi_impacts = [
        roi_impact.model_copy(
            update={
                "affected_process_ids": [
                    process_id
                    for process_id in roi_impact.affected_process_ids
                    if process_id in valid_process_set
                ]
            }
        )
        for roi_impact in roi_impacts or []
    ]

    return enterprise_tool_result(
        status="prepared",
        action="extract_project_graph_from_evidence",
        entity_type="project_graph_extraction",
        entity_id=project_id,
        summary=f"Graph extraction prepared for {project['name']}.",
        payload={
            "project_id": project_id,
            "project_name": project["name"],
            "reason": reason,
            "extraction_focus": extraction_focus or [],
            "raw_content_chars": len(raw_content),
            "process_ids": valid_process_ids,
            "entities": _clean_text_list(entities),
            "relationships": [item.model_dump() for item in relationships or []],
            "gaps": [item.model_dump() for item in scoped_gaps],
            "inconsistencies": [item.model_dump() for item in scoped_inconsistencies],
            "roi_impacts": [item.model_dump() for item in scoped_roi_impacts],
            "questions_to_validate": _clean_text_list(questions_to_validate),
            "next_action": "Review this extraction, then call manage_project_evidence with operation save_interview or save_episode if it should become project evidence.",
        },
    )


@tool
def retrieve_project_gap_context(
    project_id: str,
    query: str,
    process_id: str | None = None,
    reason: str = "Need project gap and inconsistency context.",
    limit: int = 5,
) -> str:
    """
    Retrieve project-scoped context about missing data, weak evidence,
    contradictions and validation questions. Use before asking stakeholders for
    more information or before declaring a process ready.
    """
    process_ids = [process_id] if process_id else []
    return retrieve_project_graph_context.invoke(
        {
            "project_id": project_id,
            "query": query,
            "relation_focus": "gap-and-inconsistency",
            "reason": reason,
            "entities": ["gap", "inconsistency", "missing evidence", "validation question"],
            "process_ids": process_ids,
            "include_workspace_snapshot": True,
            "include_evidence": True,
            "limit": limit,
        }
    )


@tool
def retrieve_cross_process_impact_context(
    project_id: str,
    query: str,
    process_ids: list[str] | None = None,
    reason: str = "Need cross-process impact and ROI context.",
    limit: int = 5,
) -> str:
    """
    Retrieve project-scoped context about dependencies across processes and their
    impact on deliverables, ROI, cost, cycle time, risk, quality or compliance.
    Use when several processes inside one project can change enterprise outcomes.
    """
    return retrieve_project_graph_context.invoke(
        {
            "project_id": project_id,
            "query": query,
            "relation_focus": "cross-process-impact-and-roi",
            "reason": reason,
            "entities": ["process dependency", "deliverable", "ROI", "risk", "cycle time", "cost"],
            "process_ids": process_ids or [],
            "include_workspace_snapshot": True,
            "include_evidence": True,
            "limit": limit,
        }
    )
