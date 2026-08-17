from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from backend.settings import settings
from backend.toolsets.common import format_web_results


@tool
def web_research(query: str, reason: str) -> str:
    """
    Search the web for current external information.
    Use when the user needs up-to-date external information, such as market research,
    competitors, regulations, standards, technology comparisons, recent news, or source validation.
    Do not use for consultant memory or internal project context.
    Returns a formatted web research result from Tavily, or a clear disabled/error message.
    """
    if settings.tavily_api_key is None:
        return "Web research is disabled: TAVILY_API_KEY is missing."

    tavily = TavilySearch(
        max_results=settings.tavily_max_results,
        tavily_api_key=settings.tavily_api_key,
    )
    response = tavily.invoke({"query": query})

    return format_web_results(response, reason)
