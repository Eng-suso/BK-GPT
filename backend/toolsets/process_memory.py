from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend import workspace_database
from backend.memory.episodic import episodic_store
from backend.memory.knowledge_graph import knowledge_graph_store
from backend.memory.knowledge_graph.models import (
    KnowledgeGraphClaim,
    KnowledgeGraphContradiction,
    KnowledgeGraphEvidence,
    KnowledgeGraphGap,
    KnowledgeGraphImpact,
    KnowledgeGraphQuery,
    KnowledgeGraphRelationship,
)
from backend.toolsets.workspace import enterprise_tool_result


class ProcessGraphExtractionInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Current process id.")
    raw_content: str = Field(description="Evidence text, notes, transcript or source summary to structure.")
    reason: str = Field(description="Why graph extraction is needed.")
    extraction_focus: list[str] = Field(
        default_factory=list,
        description="Focus areas: claims, handoffs, decisions, contradictions, gaps, canvas_traceability, ROI.",
    )
    entities: list[str] = Field(default_factory=list, description="Named process entities.")
    claims: list[KnowledgeGraphClaim] = Field(default_factory=list, description="Candidate process claims.")
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list, description="Candidate relations.")
    gaps: list[KnowledgeGraphGap] = Field(default_factory=list, description="Candidate evidence/modeling gaps.")
    contradictions: list[KnowledgeGraphContradiction] = Field(default_factory=list, description="Candidate contradictions.")
    impacts: list[KnowledgeGraphImpact] = Field(default_factory=list, description="Candidate business/ROI impacts.")
    questions_to_validate: list[str] = Field(default_factory=list, description="Questions needed to validate extraction.")


class SaveProcessEpisodeInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Current process id.")
    episode_type: str = Field(description="Event type: note, call, decision, interview, workshop, feedback, or observation.")
    title: str = Field(description="Short source-backed event title.")
    raw_content: str = Field(description="Original notes/transcript/source text to store as raw source custody.")
    summary: str = Field(default="", description="Concise extracted summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from raw content.")
    participants: list[str] = Field(default_factory=list, description="People, roles or teams involved.")
    entities: list[str] = Field(default_factory=list, description="Named process entities mentioned in the evidence.")
    source_refs: list[str] = Field(default_factory=list, description="Workspace source ids, document ids or external source references.")
    claims: list[KnowledgeGraphClaim] = Field(default_factory=list, description="Process claims extracted from the evidence.")
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list, description="Enterprise graph relationships.")
    gaps: list[KnowledgeGraphGap] = Field(default_factory=list, description="Missing data, missing evidence or modeling gaps.")
    contradictions: list[KnowledgeGraphContradiction] = Field(default_factory=list, description="Contradictions across evidence.")
    impacts: list[KnowledgeGraphImpact] = Field(default_factory=list, description="Business, risk or ROI impacts.")
    tags: list[str] = Field(default_factory=list, description="Additional retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class SaveProcessInterviewInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Current process id.")
    title: str = Field(description="Short interview title.")
    raw_content: str = Field(description="Original interview transcript or notes.")
    summary: str = Field(default="", description="Concise extracted interview summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from the interview.")
    participants: list[str] = Field(default_factory=list, description="Interview participants, roles or teams.")
    entities: list[str] = Field(default_factory=list, description="Named process entities mentioned in the interview.")
    source_refs: list[str] = Field(default_factory=list, description="Workspace source ids, document ids or external source references.")
    claims: list[KnowledgeGraphClaim] = Field(default_factory=list, description="Process claims extracted from the interview.")
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list, description="Enterprise graph relationships.")
    gaps: list[KnowledgeGraphGap] = Field(default_factory=list, description="Missing data, missing evidence or modeling gaps.")
    contradictions: list[KnowledgeGraphContradiction] = Field(default_factory=list, description="Contradictions across evidence.")
    impacts: list[KnowledgeGraphImpact] = Field(default_factory=list, description="Business, risk or ROI impacts.")
    tags: list[str] = Field(default_factory=list, description="Additional retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class ProcessGraphIndexInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Current process id.")
    source_title: str = Field(description="Human-readable source title.")
    raw_content: str = Field(default="", description="Source text or concise source summary.")
    reason: str = Field(description="Why this graph evidence should be indexed.")
    entities: list[str] = Field(default_factory=list, description="Named entities to index.")
    source_refs: list[str] = Field(default_factory=list, description="Workspace source ids, episode ids or document ids.")
    claims: list[KnowledgeGraphClaim] = Field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list)
    gaps: list[KnowledgeGraphGap] = Field(default_factory=list)
    contradictions: list[KnowledgeGraphContradiction] = Field(default_factory=list)
    impacts: list[KnowledgeGraphImpact] = Field(default_factory=list)


class ProcessGraphRetrievalInput(BaseModel):
    project_id: str = Field(description="Current project id.")
    process_id: str = Field(description="Current process id.")
    query: str = Field(description="Relation-heavy process retrieval question.")
    relation_focus: str = Field(
        description="Relation focus: evidence-lineage, modeling-blockers, contradiction, handoff, decision-path, canvas-traceability, ROI."
    )
    reason: str = Field(description="Why process graph retrieval is needed now.")
    entities: list[str] = Field(default_factory=list, description="Entity anchors.")
    limit: int = Field(default=8, ge=1, le=20)


def _require_process(project_id: str, process_id: str) -> dict:
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")
    if process["project_id"] != project_id:
        raise ValueError(f"Processo {process_id} non appartiene al progetto {project_id}")
    return process


def _scope_items_to_process(items: list, process_id: str) -> list:
    scoped = []
    for item in items or []:
        affected = getattr(item, "affected_process_ids", None)
        if affected is None:
            scoped.append(item)
            continue
        filtered = [value for value in affected if value == process_id]
        if filtered:
            scoped.append(item.model_copy(update={"affected_process_ids": filtered}))
    return scoped


def _clean_text_list(values: list[str] | None) -> list[str]:
    cleaned = []
    for value in values or []:
        item = " ".join(str(value or "").split())
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _process_episode_tags(
    *,
    project_id: str,
    process_id: str,
    tags: list[str] | None,
) -> list[str]:
    normalized_tags = [f"project:{project_id}", f"process:{process_id}", "process_evidence"]
    for tag in tags or []:
        normalized = " ".join(str(tag or "").split())
        if normalized and normalized not in normalized_tags:
            normalized_tags.append(normalized)
    return normalized_tags


def _save_process_episode_payload(
    *,
    action: str,
    entity_type: str,
    project_id: str,
    process_id: str,
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    entities: list[str] | None = None,
    source_refs: list[str] | None = None,
    claims: list[KnowledgeGraphClaim] | None = None,
    relationships: list[KnowledgeGraphRelationship] | None = None,
    gaps: list[KnowledgeGraphGap] | None = None,
    contradictions: list[KnowledgeGraphContradiction] | None = None,
    impacts: list[KnowledgeGraphImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    process = _require_process(project_id, process_id)
    scoped_gaps = _scope_items_to_process(gaps or [], process_id)
    scoped_contradictions = _scope_items_to_process(contradictions or [], process_id)
    scoped_impacts = _scope_items_to_process(impacts or [], process_id)
    graph_payload_present = bool(claims or relationships or scoped_gaps or scoped_contradictions or scoped_impacts or entities)
    kg_index_result = None

    if graph_payload_present:
        kg_index_result = knowledge_graph_store.index_evidence_graph(
            KnowledgeGraphEvidence(
                project_id=project_id,
                scope="process",
                source_title=title,
                raw_content=raw_content,
                reason=f"{action}: {summary or title}",
                process_ids=[process_id],
                entities=entities or [],
                source_refs=source_refs or [],
                claims=claims or [],
                relationships=relationships or [],
                gaps=scoped_gaps,
                contradictions=scoped_contradictions,
                impacts=scoped_impacts,
            )
        )

    memory_result = episodic_store.save_episode_memory(
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights or [],
        participants=participants or [],
        project=project_id,
        tags=_process_episode_tags(
            project_id=project_id,
            process_id=process_id,
            tags=[
                *(tags or []),
                *[f"entity:{item}" for item in _clean_text_list(entities)],
                *(["graph:claims"] if claims else []),
                *(["graph:relationships"] if relationships else []),
                *(["graph:gaps"] if scoped_gaps else []),
                *(["graph:contradictions"] if scoped_contradictions else []),
                *(["graph:impacts"] if scoped_impacts else []),
            ],
        ),
        occurred_at=occurred_at,
    )

    return enterprise_tool_result(
        status="saved",
        action=action,
        entity_type=entity_type,
        entity_id=process_id,
        summary=f"Evidence saved for process {process['name']}: {title}",
        payload={
            "project_id": project_id,
            "process_id": process_id,
            "process_name": process["name"],
            "episode_type": episode_type,
            "title": title,
            "entities": _clean_text_list(entities),
            "source_refs": source_refs or [],
            "claims": [item.model_dump(mode="json") for item in claims or []],
            "relationships": [item.model_dump(mode="json") for item in relationships or []],
            "gaps": [item.model_dump(mode="json") for item in scoped_gaps],
            "contradictions": [item.model_dump(mode="json") for item in scoped_contradictions],
            "impacts": [item.model_dump(mode="json") for item in scoped_impacts],
            "knowledge_graph_index": kg_index_result,
            "memory_result": memory_result,
        },
        next_actions=[
            {
                "owner": "evidence_subgraph",
                "action": "Synthesize evidence coverage, contradictions and modeling blockers.",
            },
            {
                "owner": "modeling_subgraph",
                "action": "Use retrieved graph context before preparing ProcessUnderstanding.",
            },
        ],
    )


@tool(args_schema=SaveProcessEpisodeInput)
def save_process_episode(
    project_id: str,
    process_id: str,
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    entities: list[str] | None = None,
    source_refs: list[str] | None = None,
    claims: list[KnowledgeGraphClaim] | None = None,
    relationships: list[KnowledgeGraphRelationship] | None = None,
    gaps: list[KnowledgeGraphGap] | None = None,
    contradictions: list[KnowledgeGraphContradiction] | None = None,
    impacts: list[KnowledgeGraphImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save process-scoped episodic evidence with raw source custody and optional
    enterprise Knowledge Graph indexing. Use for real notes, calls, workshops,
    observations, decisions, examples or source-backed process evidence.
    """
    return _save_process_episode_payload(
        action="save_process_episode",
        entity_type="process_episode",
        project_id=project_id,
        process_id=process_id,
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights,
        participants=participants,
        entities=entities,
        source_refs=source_refs,
        claims=claims,
        relationships=relationships,
        gaps=gaps,
        contradictions=contradictions,
        impacts=impacts,
        tags=tags,
        occurred_at=occurred_at,
    )


@tool(args_schema=SaveProcessInterviewInput)
def save_process_interview(
    project_id: str,
    process_id: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    entities: list[str] | None = None,
    source_refs: list[str] | None = None,
    claims: list[KnowledgeGraphClaim] | None = None,
    relationships: list[KnowledgeGraphRelationship] | None = None,
    gaps: list[KnowledgeGraphGap] | None = None,
    contradictions: list[KnowledgeGraphContradiction] | None = None,
    impacts: list[KnowledgeGraphImpact] | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save a process-scoped interview with raw transcript custody and optional
    enterprise Knowledge Graph indexing. Use when Process Chat receives interview
    notes/transcripts that should support discovery, evidence synthesis or As-Is modeling.
    """
    return _save_process_episode_payload(
        action="save_process_interview",
        entity_type="process_interview",
        project_id=project_id,
        process_id=process_id,
        episode_type="interview",
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights or [],
        participants=participants or [],
        entities=entities or [],
        source_refs=source_refs or [],
        claims=claims or [],
        relationships=relationships or [],
        gaps=gaps or [],
        contradictions=contradictions or [],
        impacts=impacts or [],
        tags=["interview", *(tags or [])],
        occurred_at=occurred_at,
    )


@tool(args_schema=ProcessGraphExtractionInput)
def extract_process_graph_from_evidence(
    project_id: str,
    process_id: str,
    raw_content: str,
    reason: str,
    extraction_focus: list[str] | None = None,
    entities: list[str] | None = None,
    claims: list[KnowledgeGraphClaim] | None = None,
    relationships: list[KnowledgeGraphRelationship] | None = None,
    gaps: list[KnowledgeGraphGap] | None = None,
    contradictions: list[KnowledgeGraphContradiction] | None = None,
    impacts: list[KnowledgeGraphImpact] | None = None,
    questions_to_validate: list[str] | None = None,
) -> str:
    """
    Prepare a process-scoped enterprise graph extraction from evidence. The LLM
    supplies candidate claims, relationships, gaps, contradictions and impacts.
    This tool validates scope and returns a review; it does not index automatically.
    """
    process = _require_process(project_id, process_id)
    scoped_gaps = _scope_items_to_process(gaps or [], process_id)
    scoped_contradictions = _scope_items_to_process(contradictions or [], process_id)
    scoped_impacts = _scope_items_to_process(impacts or [], process_id)

    return enterprise_tool_result(
        status="prepared",
        action="extract_process_graph_from_evidence",
        entity_type="process_graph_extraction",
        entity_id=process_id,
        summary=f"Process graph extraction prepared for {process['name']}.",
        payload={
            "project_id": project_id,
            "process_id": process_id,
            "process_name": process["name"],
            "reason": reason,
            "extraction_focus": extraction_focus or [],
            "raw_content_chars": len(raw_content),
            "entities": entities or [],
            "claims": [item.model_dump(mode="json") for item in claims or []],
            "relationships": [item.model_dump(mode="json") for item in relationships or []],
            "gaps": [item.model_dump(mode="json") for item in scoped_gaps],
            "contradictions": [item.model_dump(mode="json") for item in scoped_contradictions],
            "impacts": [item.model_dump(mode="json") for item in scoped_impacts],
            "questions_to_validate": questions_to_validate or [],
            "next_action": "Review this extraction, then call index_process_evidence_graph if it should become graph evidence.",
        },
    )


@tool(args_schema=ProcessGraphIndexInput)
def index_process_evidence_graph(
    project_id: str,
    process_id: str,
    source_title: str,
    reason: str,
    raw_content: str = "",
    entities: list[str] | None = None,
    source_refs: list[str] | None = None,
    claims: list[KnowledgeGraphClaim] | None = None,
    relationships: list[KnowledgeGraphRelationship] | None = None,
    gaps: list[KnowledgeGraphGap] | None = None,
    contradictions: list[KnowledgeGraphContradiction] | None = None,
    impacts: list[KnowledgeGraphImpact] | None = None,
) -> str:
    """
    Index process-scoped graph evidence into the enterprise knowledge graph.
    Use after evidence extraction has been reviewed enough to become retrieval
    context. This is the process-facing GraphRAG ingestion facade.
    """
    process = _require_process(project_id, process_id)
    scoped_gaps = _scope_items_to_process(gaps or [], process_id)
    scoped_contradictions = _scope_items_to_process(contradictions or [], process_id)
    scoped_impacts = _scope_items_to_process(impacts or [], process_id)
    result = knowledge_graph_store.index_evidence_graph(
        KnowledgeGraphEvidence(
            project_id=project_id,
            scope="process",
            source_title=source_title,
            raw_content=raw_content,
            reason=reason,
            process_ids=[process_id],
            entities=entities or [],
            source_refs=source_refs or [],
            claims=claims or [],
            relationships=relationships or [],
            gaps=scoped_gaps,
            contradictions=scoped_contradictions,
            impacts=scoped_impacts,
        )
    )
    return enterprise_tool_result(
        status="indexed",
        action="index_process_evidence_graph",
        entity_type="process_knowledge_graph",
        entity_id=process_id,
        summary=f"Graph evidence indexed for {process['name']}.",
        payload=result,
    )


@tool(args_schema=ProcessGraphRetrievalInput)
def retrieve_process_graph_context(
    project_id: str,
    process_id: str,
    query: str,
    relation_focus: str,
    reason: str,
    entities: list[str] | None = None,
    limit: int = 8,
) -> str:
    """
    Retrieve process-scoped enterprise Knowledge Graph context. Use for
    relation-heavy process questions: evidence lineage, supported activities,
    handoffs, decisions, contradictions, modeling blockers and canvas mapping.
    """
    process = _require_process(project_id, process_id)
    context = knowledge_graph_store.retrieve_graph_context(
        KnowledgeGraphQuery(
            project_id=project_id,
            query=query,
            relation_focus=relation_focus,
            reason=reason,
            process_ids=[process_id],
            entities=entities or [],
            limit=limit,
        )
    )
    return enterprise_tool_result(
        status=context.status,
        action="retrieve_process_graph_context",
        entity_type="process_graph_context",
        entity_id=process_id,
        summary=f"Process KG retrieval for {process['name']}: {relation_focus}",
        payload={
            "project_id": project_id,
            "process_id": process_id,
            "process_name": process["name"],
            "reason": reason,
            "context": context.model_dump(mode="json"),
        },
    )


@tool
def retrieve_process_gap_context(
    project_id: str,
    process_id: str,
    query: str,
    reason: str = "Need process gaps and missing evidence before modeling.",
    limit: int = 8,
) -> str:
    """
    Retrieve graph context about process gaps, missing evidence and modeling blockers.
    Use before declaring ProcessUnderstanding ready.
    """
    return retrieve_process_graph_context.invoke(
        {
            "project_id": project_id,
            "process_id": process_id,
            "query": query,
            "relation_focus": "gap-to-modeling",
            "reason": reason,
            "entities": ["gap", "missing evidence", "modeling blocker", "unknown"],
            "limit": limit,
        }
    )


@tool
def retrieve_process_contradiction_context(
    project_id: str,
    process_id: str,
    query: str,
    reason: str = "Need process contradictions before modeling.",
    limit: int = 8,
) -> str:
    """
    Retrieve graph context about contradictory claims and source disagreement.
    Use before creating or updating an As-Is model.
    """
    return retrieve_process_graph_context.invoke(
        {
            "project_id": project_id,
            "process_id": process_id,
            "query": query,
            "relation_focus": "contradiction",
            "reason": reason,
            "entities": ["contradiction", "conflicting claim", "source disagreement"],
            "limit": limit,
        }
    )


@tool
def retrieve_process_canvas_traceability_context(
    project_id: str,
    process_id: str,
    query: str,
    reason: str = "Need evidence lineage from process semantics to BPMN/canvas.",
    limit: int = 8,
) -> str:
    """
    Retrieve graph context linking process claims and elements to BPMN/canvas
    elements. Use before canvas handoff or when explaining why a BPMN element exists.
    """
    return retrieve_process_graph_context.invoke(
        {
            "project_id": project_id,
            "process_id": process_id,
            "query": query,
            "relation_focus": "canvas-traceability",
            "reason": reason,
            "entities": ["BPMN", "canvas", "ProcessUnderstanding", "claim", "activity", "handoff"],
            "limit": limit,
        }
    )


process_memory_tools = [
    save_process_interview,
    save_process_episode,
    extract_process_graph_from_evidence,
    index_process_evidence_graph,
    retrieve_process_graph_context,
    retrieve_process_gap_context,
    retrieve_process_contradiction_context,
    retrieve_process_canvas_traceability_context,
]
