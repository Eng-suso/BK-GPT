from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from backend.settings import settings
from backend.memory.semantic.semantic_store import (
    delete_consultant_memory,
    save_consultant_memory,
    search_consultant_memory,
    save_bpmn_preference,
    search_bpmn_preferences,
)
from backend.memory.episodic.episodic_store import (
    save_episode_memory,
    search_episode_memory,
    save_interview_memory,
    search_interview_memory,
)

def format_web_results(response, reason: str) -> str:
    return f"Ricerca web eseguita per: {reason}\n\n{response}"

@tool
def web_research(query: str, reason: str) -> str:
    """
    Search the web for current external information.
    Use only for market, competitor, regulatory, technology, news, or source-validation questions.
    Do not use for consultant memory or internal project context.
    """
    if settings.tavily_api_key is None:
        return "Web research is disabled: TAVILY_API_KEY is missing."

    tavily = TavilySearch(
        max_results=settings.tavily_max_results,
        tavily_api_key=settings.tavily_api_key,
    )
    response = tavily.invoke({"query": query})

    return format_web_results(response, reason)

@tool
def remember_consultant_fact(content: str, category: str) -> str:
    """Save a durable semantic memory about the consultant."""
    return save_consultant_memory(content=content, category=category)


@tool
def recall_consultant_memory(query: str, category: str | None = None) -> str:
    """Search durable semantic memories about the consultant."""
    return search_consultant_memory(query=query, category=category)


@tool
def forget_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    """
    Delete one specific semantic memory by its Mem0 memory_id.
    Use only when the user explicitly asks to remove a specific memory.
    If the user did not provide a memory_id, search memory first and ask which memory to delete.
    """
    return delete_consultant_memory(memory_id=memory_id, delete_linked=delete_linked)


@tool
def remember_bpmn_preference(rule: str, area: str) -> str:
    """Save a BPMN/process modeling preference for this consultant."""
    return save_bpmn_preference(rule=rule, area=area)


@tool
def recall_bpmn_preferences(query: str, area: str | None = None) -> str:
    """Search BPMN/process modeling preferences for this consultant."""
    return search_bpmn_preferences(query=query, area=area)


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
    Use for dated events such as calls, notes, decisions, experiments, and feedback.
    Do not use for stable consultant profile facts or generic preferences.
    """
    return save_episode_memory(
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
    Use when the user asks about past calls, notes, interviews, decisions, evidence, or context from a dated event.
    """
    return search_episode_memory(
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
    Keep the transcript or notes as raw_content; use summary and insights only for extracted context.
    """
    return save_interview_memory(
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
    Use for customer language, discovery evidence, recurring pain points, objections, and interview provenance.
    """
    return search_interview_memory(
        query=query,
        project=project,
        limit=limit,
    )


tools = [
    remember_consultant_fact,
    recall_consultant_memory,
    forget_consultant_memory,
    remember_bpmn_preference,
    recall_bpmn_preferences,
    save_episode,
    search_episodes,
    save_interview,
    search_interviews,
    web_research,
]
