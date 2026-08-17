from langchain_core.tools import tool

from backend.memory.episodic import episodic_store
from backend.memory.semantic import semantic_store


@tool
def remember_consultant_fact(content: str, category: str) -> str:
    """
    Save a durable semantic memory about the consultant.
    Use when the user shares stable information that should affect future answers:
    identity, positioning, target clients, offers, sales method, delivery method,
    communication style, preferences, recurring constraints, or DeliR usage preferences.
    Do not use for raw transcripts, dated events, temporary details, or external facts.
    Returns a confirmation message, or a clear disabled/error message if Mem0 is unavailable.
    """
    return semantic_store.save_consultant_memory(content=content, category=category)


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


@tool
def save_episode(
    episode_type: str,
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
    Save an episodic memory with raw source custody and Mem0 semantic indexing.
    Use for dated, source-backed events such as calls, meeting notes, decisions,
    experiments, feedback, observations, or project moments.
    Put the original notes/transcript in raw_content. Put only extracted context in
    summary and insights. Use participants, project, tags, and occurred_at for provenance.
    Do not use for stable consultant profile facts, generic preferences, or web research.
    Returns episode_id/source_id confirmation plus Mem0 indexing result.
    """
    return episodic_store.save_episode_memory(
        episode_type=episode_type,
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
    forget_consultant_memory,
    remember_bpmn_preference,
    search_bpmn_preferences,
    save_episode,
    search_episodes,
    save_interview,
    search_interviews,
]
