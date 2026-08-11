from mem0 import MemoryClient

from backend.settings import settings


_client = (
    MemoryClient(api_key=settings.mem0_api_key)
    if settings.mem0_api_key
    else None
)


def format_memory_results(response, limit: int = 5) -> str:
    if not response:
        return "Non ho trovato memorie rilevanti."

    if isinstance(response, dict):
        results = response.get("results") or response.get("memories") or []
    else:
        results = response

    if not results:
        return "Non ho trovato memorie rilevanti."

    lines = []

    for item in results[:limit]:
        if isinstance(item, dict):
            memory = (
                item.get("memory")
                or item.get("text")
                or item.get("content")
                or str(item)
            )
            lines.append(f"- {memory}")
        else:
            lines.append(f"- {item}")

    return "Ho trovato queste memorie rilevanti:\n" + "\n".join(lines)


def save_consultant_memory(content: str, category: str) -> str:
    if _client is None:
        return "Memoria semantica disattivata: manca MEM0_API_KEY."

    _client.add(
        messages=[
            {
                "role": "user",
                "content": f"[{category}] {content}",
            }
        ],
        user_id=settings.mem0_user_id,
    )

    return f"Ho salvato in memoria: {content}"


def search_consultant_memory(query: str, category: str | None = None) -> str:
    if _client is None:
        return "Memoria semantica disattivata: manca MEM0_API_KEY."

    search_query = f"[{category}] {query}" if category else query

    response = _client.search(
        query=search_query,
        user_id=settings.mem0_user_id,
    )

    return format_memory_results(response)


def save_bpmn_preference(rule: str, area: str) -> str:
    return save_consultant_memory(
        content=rule,
        category=f"bpmn:{area}",
    )


def search_bpmn_preferences(query: str, area: str | None = None) -> str:
    category = f"bpmn:{area}" if area else "bpmn"
    return search_consultant_memory(
        query=query,
        category=category,
    )
