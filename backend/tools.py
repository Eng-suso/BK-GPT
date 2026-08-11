from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from backend import settings
from backend.memory.semantic.semantic_store import (
    save_consultant_memory,
    search_consultant_memory,
    save_bpmn_preference,
    search_bpmn_preferences,
)

_tavily = (
    TavilySearch(max_results=settings.tavily_max_results)
    if settings.tavily_api_key
    else None
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
    if _tavily is None:
        return "Web research is disabled: TAVILY_API_KEY is missing."

    response = _tavily.invoke({"query": query})

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
def remember_bpmn_preference(rule: str, area: str) -> str:
    """Save a BPMN/process modeling preference for this consultant."""
    return save_bpmn_preference(rule=rule, area=area)


@tool
def recall_bpmn_preferences(query: str, area: str | None = None) -> str:
    """Search BPMN/process modeling preferences for this consultant."""
    return search_bpmn_preferences(query=query, area=area)


tools = [
    remember_consultant_fact,
    recall_consultant_memory,
    remember_bpmn_preference,
    recall_bpmn_preferences,
]