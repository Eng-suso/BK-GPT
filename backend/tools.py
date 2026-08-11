from langchain_core.tools import tool

from backend.memory.semantic.semantic_store import (
    save_consultant_memory,
    search_consultant_memory,
    save_bpmn_preference,
    search_bpmn_preferences,
)


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