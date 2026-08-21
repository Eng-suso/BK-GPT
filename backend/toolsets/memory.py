from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.memory.episodic import episodic_store
from backend.memory.models import (
    ConsultantSemanticMemory,
    ConsultingContextRetrievalRequest,
    ConsultingGraphRetrievalRequest,
    EpisodeMemory,
)
from backend.memory.semantic import semantic_store
from backend.toolsets.workspace import enterprise_tool_result, get_workspace_overview


class RememberConsultantFactInput(BaseModel):
    content: str = Field(description="One durable consultant-level fact, preference, rule, or stable pattern.")
    category: str = Field(description="Stable category, such as positioning, delivery_method, sales_method, or preference.")
    entity_names: list[str] = Field(default_factory=list, description="Named entities for Mem0 Graph Memory linking.")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence this should affect future turns.")
    source: str = Field(default="chat", description="Where this memory came from.")
    durability: str = Field(default="stable", description="stable, preference, profile, method, or working_assumption.")


class SaveEpisodeInput(BaseModel):
    episode_type: str = Field(description="Event type: call, note, decision, experiment, feedback, or interview.")
    title: str = Field(description="Short source-backed event title.")
    raw_content: str = Field(description="Original notes/transcript/source text. Stored as local raw source custody.")
    summary: str = Field(default="", description="Concise extracted summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from raw content.")
    participants: list[str] = Field(default_factory=list, description="People or roles involved.")
    project: str | None = Field(default=None, description="Related project name or id.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class ManageConsultingEvidenceInput(BaseModel):
    operation: str = Field(
        description=(
            "Evidence lifecycle operation. Use list/search/inspect to retrieve source-backed evidence; "
            "use save_interview or save_episode to store new raw evidence; use update_metadata for labels; "
            "use archive for normal removal from active retrieval; use restore to reactivate; use delete only "
            "after the user explicitly confirms destructive deletion."
        )
    )
    episode_id: str | None = Field(default=None, description="Target episode_id for inspect, update_metadata, archive, restore, or delete.")
    source_id: str | None = Field(default=None, description="Optional source_id for inspect when episode_id is unknown.")
    query: str = Field(default="", description="Search/list query. Leave empty to list recent evidence.")
    episode_type: str | None = Field(default=None, description="Filter or save type: interview, call, note, decision, workshop, feedback, observation.")
    title: str = Field(default="", description="Evidence title for save/update.")
    raw_content: str = Field(default="", description="Original notes/transcript/source text for save operations.")
    summary: str = Field(default="", description="Concise extracted summary for save/update.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights for save/update.")
    participants: list[str] = Field(default_factory=list, description="People, roles or teams involved.")
    project: str | None = Field(default=None, description="Optional project name/id for consulting-level evidence.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags for save/update.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")
    status: str = Field(default="active", description="For list: active, archived, or any.")
    reason: str = Field(default="", description="Why this lifecycle action is being taken, especially archive/delete.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum evidence records to return.")
    include_source_text: bool = Field(default=False, description="For inspect: include raw source text when needed.")
    confirm_destructive_action: bool = Field(default=False, description="Required for hard delete. Prefer archive for ordinary removal.")
    delete_raw_source: bool = Field(default=False, description="Also delete local raw source file during confirmed hard delete.")


@tool(args_schema=RememberConsultantFactInput)
def remember_consultant_fact(
    content: str,
    category: str,
    entity_names: list[str] | None = None,
    confidence: float = 0.8,
    source: str = "chat",
    durability: str = "stable",
) -> str:
    """
    Save a durable semantic memory about the consultant.
    Use when the user shares stable information that should affect future answers:
    identity, positioning, target clients, offers, sales method, delivery method,
    communication style, preferences, recurring constraints, or DeliR usage preferences.
    Do not use for raw transcripts, dated events, temporary details, or external facts.
    Include entity_names to improve Mem0 Graph Memory/entity linking.
    Returns a confirmation message, or a clear disabled/error message if Mem0 is unavailable.
    """
    allowed_durability = {"stable", "preference", "profile", "method", "working_assumption"}
    memory = ConsultantSemanticMemory(
        category=category,
        statement=content,
        entity_names=entity_names or [],
        confidence=confidence,
        source=source,
        durability=durability if durability in allowed_durability else "stable",
    )
    return semantic_store.save_structured_consultant_memory(memory)


@tool
def search_consultant_memory(query: str, category: str | None = None) -> str:
    """
    Search durable semantic memories about the consultant.
    Use before answering questions about the consultant's preferences, identity,
    positioning, offers, target clients, sales method, delivery method, communication
    style, recurring constraints, DeliR usage, or other stable internal context.
    Do not use for dated interviews, call transcripts, source evidence, or web facts.
    Returns formatted internal memory context with memory_ids when available, or a clear
    no-results/disabled/error message.
    """
    return semantic_store.search_consultant_memory(query=query, category=category)


@tool(args_schema=ConsultingContextRetrievalRequest)
def retrieve_consulting_context(
    query: str,
    retrieval_scope: str = "both",
    category: str | None = None,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
    reason: str = "",
) -> str:
    """
    Retrieve consultant context through one structured facade.
    Use this in Consulting scope before answering questions that may depend on
    stable consultant memory, past events, interviews, source-backed evidence, or both.
    Use semantic for durable profile/method/preference context.
    Use episodic or interview for dated source-backed context.
    Use both when the user asks for synthesis across stable memory and past events.
    """
    request = ConsultingContextRetrievalRequest(
        query=query,
        retrieval_scope=retrieval_scope,
        category=category,
        episode_type=episode_type,
        project=project,
        limit=limit,
        reason=reason or "Consulting context retrieval.",
    )
    sections = [
        "CONSULTING CONTEXT RETRIEVAL",
        f"reason: {request.reason}",
        f"scope: {request.retrieval_scope}",
    ]

    if request.retrieval_scope in {"semantic", "both"}:
        sections.extend(
            [
                "",
                "SEMANTIC MEMORY",
                semantic_store.search_consultant_memory(
                    query=request.query,
                    category=request.category,
                ),
            ]
        )

    if request.retrieval_scope in {"episodic", "both"}:
        sections.extend(
            [
                "",
                "EPISODIC MEMORY",
                episodic_store.search_episode_memory(
                    query=request.query,
                    episode_type=request.episode_type,
                    project=request.project,
                    limit=request.limit,
                ),
            ]
        )

    if request.retrieval_scope == "interview":
        sections.extend(
            [
                "",
                "INTERVIEW MEMORY",
                episodic_store.search_interview_memory(
                    query=request.query,
                    project=request.project,
                    limit=request.limit,
                ),
            ]
        )

    return "\n".join(sections)


@tool(args_schema=ConsultingGraphRetrievalRequest)
def retrieve_consulting_graph_context(
    query: str,
    relation_focus: str,
    reason: str,
    entities: list[str] | None = None,
    include_workspace_overview: bool = True,
    limit: int = 5,
) -> str:
    """
    Retrieve relational consulting context through Mem0 Graph Memory-style retrieval plus optional workspace grounding.

    Use this tool when the user asks a relation-heavy question or when routing/synthesis depends on relationships, for example:
    - which clients, projects, processes, sources, decisions, risks, offers, or insights are connected;
    - which evidence supports an insight or decision;
    - which projects share a recurring pain, risk, objection, or delivery pattern;
    - how Sohay's preferences, positioning, offers, ICP, or delivery method connect to current workspace work.

    Do not use this tool for simple factual lookup, simple workspace CRUD, BPMN editing, or external/current web information.
    Do not treat Mem0 as the operational source of truth: use workspace tools for authoritative clients/projects/processes.
    """
    request = ConsultingGraphRetrievalRequest(
        query=query,
        entities=entities or [],
        relation_focus=relation_focus,
        reason=reason,
        include_workspace_overview=include_workspace_overview,
        limit=limit,
    )
    entity_query = " ".join(request.entities)
    relational_query = "\n".join(
        [
            f"relation_focus: {request.relation_focus}",
            f"entities: {entity_query or 'none'}",
            f"query: {request.query}",
        ]
    )
    semantic_result = semantic_store.search_consultant_memory(
        query=relational_query,
        category=None,
    )
    episodic_result = episodic_store.search_episode_memory(
        query=entity_query or request.query,
        limit=request.limit,
    )
    workspace_result = (
        get_workspace_overview.invoke({})
        if request.include_workspace_overview
        else "Workspace overview not requested."
    )

    return "\n".join(
        [
            "CONSULTING GRAPH CONTEXT RETRIEVAL",
            "source: mem0_graph_memory_plus_workspace_grounding",
            f"reason: {request.reason}",
            f"relation_focus: {request.relation_focus}",
            f"entities: {', '.join(request.entities) or 'none'}",
            "",
            "MEM0 RELATIONAL MEMORY",
            semantic_result,
            "",
            "EPISODIC EVIDENCE LINKS",
            episodic_result,
            "",
            "WORKSPACE GROUNDING",
            workspace_result,
            "",
            "CAVEAT",
            "Use Mem0 results as relational retrieval context. Use workspace DB records as authoritative operational state.",
        ]
    )


@tool
def forget_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    """
    Delete one specific semantic memory by its Mem0 memory_id.
    Use only when the user explicitly asks to remove a specific durable memory.
    If the user did not provide a memory_id, search memory first and ask which memory to delete.
    Do not use for ordinary corrections, edits, or forgetting a whole category.
    Returns a deletion confirmation, or a clear disabled/error message.
    """
    return semantic_store.delete_consultant_memory(memory_id=memory_id, delete_linked=delete_linked)


@tool(args_schema=ManageConsultingEvidenceInput)
def manage_consulting_evidence(
    operation: str,
    episode_id: str | None = None,
    source_id: str | None = None,
    query: str = "",
    episode_type: str | None = None,
    title: str = "",
    raw_content: str = "",
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    project: str | None = None,
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
    Manage consulting-level source-backed evidence through one lifecycle facade.
    Use this for interviews, calls, notes, decisions, workshops, observations and
    other episodic evidence. Do not use it for durable consultant profile facts,
    preferences, methods or BPMN rules; those remain semantic memory tools.
    Prefer archive over delete when the user asks to remove evidence from active use.
    Hard delete requires confirm_destructive_action=True.
    """
    normalized_operation = operation.strip().lower()
    normalized_status = status if status in {"active", "archived", "any"} else "active"

    if normalized_operation in {"list", "search"}:
        evidence = episodic_store.list_episode_memory(
            project=project,
            episode_type=episode_type,
            query=query,
            status=normalized_status,
            limit=limit,
        )
        return enterprise_tool_result(
            status="ok",
            action="manage_consulting_evidence",
            entity_type="consulting_evidence_collection",
            summary=f"Consulting evidence {normalized_operation}: {len(evidence)} record.",
            payload={
                "operation": normalized_operation,
                "query": query,
                "project": project,
                "episode_type": episode_type,
                "status": normalized_status,
                "evidence": evidence,
            },
        )

    if normalized_operation == "inspect":
        evidence = episodic_store.get_episode_memory(
            episode_id=episode_id,
            source_id=source_id,
            include_source_text=include_source_text,
        )
        return enterprise_tool_result(
            status="ok" if evidence else "not_found",
            action="manage_consulting_evidence",
            entity_type="consulting_evidence",
            entity_id=episode_id,
            summary="Consulting evidence inspected." if evidence else "Consulting evidence not found.",
            payload={"operation": normalized_operation, "evidence": evidence},
        )

    if normalized_operation in {"save_interview", "save_episode"}:
        if not raw_content.strip():
            return enterprise_tool_result(
                status="blocked",
                action="manage_consulting_evidence",
                entity_type="consulting_evidence",
                summary="Cannot save evidence without raw_content.",
                payload={"operation": normalized_operation},
            )
        save_result = episodic_store.save_episode_memory(
            episode_type="interview" if normalized_operation == "save_interview" else (episode_type or "note"),
            title=title,
            raw_content=raw_content,
            summary=summary,
            insights=insights or [],
            participants=participants or [],
            project=project,
            tags=["interview", *(tags or [])] if normalized_operation == "save_interview" else (tags or []),
            occurred_at=occurred_at,
        )
        return enterprise_tool_result(
            status="saved",
            action="manage_consulting_evidence",
            entity_type="consulting_interview" if normalized_operation == "save_interview" else "consulting_episode",
            summary=f"Consulting evidence saved: {title or 'untitled'}",
            payload={"operation": normalized_operation, "memory_result": save_result},
        )

    if normalized_operation == "update_metadata":
        result = episodic_store.update_episode_metadata(
            episode_id=episode_id or "",
            title=title if title else None,
            summary=summary if summary else None,
            insights=insights if insights else None,
            participants=participants if participants else None,
            project=project,
            tags=tags if tags else None,
            occurred_at=occurred_at,
        )
        return enterprise_tool_result(
            status=result["status"],
            action="manage_consulting_evidence",
            entity_type="consulting_evidence",
            entity_id=episode_id,
            summary=result["message"],
            payload={"operation": normalized_operation, "result": result},
        )

    if normalized_operation == "archive":
        result = episodic_store.archive_episode_memory(episode_id=episode_id or "", reason=reason)
    elif normalized_operation == "restore":
        result = episodic_store.restore_episode_memory(episode_id=episode_id or "")
    elif normalized_operation == "delete":
        result = episodic_store.delete_episode_memory(
            episode_id=episode_id or "",
            confirm_destructive_action=confirm_destructive_action,
            delete_raw_source=delete_raw_source,
        )
    else:
        result = {
            "status": "blocked",
            "message": f"Unsupported operation: {operation}.",
        }

    return enterprise_tool_result(
        status=result["status"],
        action="manage_consulting_evidence",
        entity_type="consulting_evidence",
        entity_id=episode_id,
        summary=result["message"],
        payload={"operation": normalized_operation, "result": result},
    )


@tool
def remember_bpmn_preference(rule: str, area: str) -> str:
    """
    Save a durable BPMN/process modeling preference for this consultant.
    Use when the user states a stable preference or rule about BPMN style, gateways,
    events, lanes, pools, handoffs, exceptions, assumptions, readiness, validation,
    evidence policy, or process-discovery method.
    Do not use for a one-off process detail or raw interview/call evidence.
    Returns a confirmation message, or a clear disabled/error message if Mem0 is unavailable.
    """
    return semantic_store.save_bpmn_preference(rule=rule, area=area)


@tool
def search_bpmn_preferences(query: str, area: str | None = None) -> str:
    """
    Search durable BPMN/process modeling preferences for this consultant.
    Use before answering questions about how the consultant prefers BPMN/process models
    to be structured, validated, scoped, evidenced, or communicated.
    Do not use for generic BPMN knowledge, current standards/news, or raw interview evidence.
    Returns formatted internal BPMN preference context, or a clear no-results/disabled/error message.
    """
    return semantic_store.search_bpmn_preferences(query=query, area=area)


@tool(args_schema=SaveEpisodeInput)
def save_episode(
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save an episodic memory with raw source custody and Mem0 semantic indexing.
    Use for dated, source-backed events such as calls, meeting notes, decisions,
    experiments, feedback, observations, or project moments.
    Put the original notes/transcript in raw_content. Put only extracted context in
    summary and insights. Use participants, project, tags, and occurred_at for provenance.
    Do not use for stable consultant profile facts, generic preferences, or web research.
    Returns episode_id/source_id confirmation plus Mem0 indexing result.
    """
    memory = EpisodeMemory(
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights or [],
        participants=participants or [],
        project=project,
        tags=tags or [],
        occurred_at=occurred_at,
    )
    return episodic_store.save_structured_episode_memory(memory)


@tool
def search_episodes(
    query: str,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
) -> str:
    """
    Search episodic memories by semantic query and local source registry.
    Use when the user asks what happened in a past event, what was said in a call/note,
    where an insight came from, which source supports an observation, or what prior
    decisions/feedback/experiments exist.
    Use episode_type to narrow to call, note, decision, experiment, feedback, or interview.
    Do not use for stable consultant preferences or profile-level facts unless the user
    asks for source evidence.
    Returns Mem0 episodic results plus local registry matches with episode_id, source_id,
    date, participants, project, tags, summary, insights, and source_path when available.
    """
    return episodic_store.search_episode_memory(
        query=query,
        episode_type=episode_type,
        project=project,
        limit=limit,
    )


@tool
def save_interview(
    title: str,
    raw_content: str,
    summary: str = "",
    insights: str = "",
    participants: str = "",
    project: str | None = None,
    tags: str = "",
    occurred_at: str | None = None,
) -> str:
    """
    Save an interview as episodic memory.
    Use for customer/prospect/user/consultant interviews, discovery transcripts, or
    interview notes. Keep the transcript or original notes in raw_content; use summary
    and insights only for extracted context. Use participants, project, tags, and
    occurred_at for provenance.
    Do not use for stable preferences unless the interview insight has been confirmed
    as durable memory separately.
    Returns episode_id/source_id confirmation plus Mem0 indexing result.
    """
    return episodic_store.save_interview_memory(
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights,
        participants=participants,
        project=project,
        tags=tags,
        occurred_at=occurred_at,
    )


@tool
def search_interviews(
    query: str,
    project: str | None = None,
    limit: int = 5,
) -> str:
    """
    Search saved interviews.
    Use when the user asks about interview evidence, customer language, discovery findings,
    recurring pain points, objections, needs, quotes/context, or where an interview insight
    came from.
    Do not use for generic consultant preferences unless the user asks for interview-backed evidence.
    Returns Mem0 interview results plus local registry matches with episode_id, source_id,
    date, participants, project, tags, summary, insights, and source_path when available.
    """
    return episodic_store.search_interview_memory(
        query=query,
        project=project,
        limit=limit,
    )


memory_tools = [
    remember_consultant_fact,
    search_consultant_memory,
    retrieve_consulting_context,
    retrieve_consulting_graph_context,
    forget_consultant_memory,
    manage_consulting_evidence,
    remember_bpmn_preference,
    search_bpmn_preferences,
    save_episode,
    search_episodes,
    save_interview,
    search_interviews,
]
