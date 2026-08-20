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
from backend.toolsets.workspace import get_workspace_overview


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
    remember_bpmn_preference,
    search_bpmn_preferences,
    save_episode,
    search_episodes,
    save_interview,
    search_interviews,
]
