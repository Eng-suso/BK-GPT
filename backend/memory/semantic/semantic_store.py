from mem0 import MemoryClient

from backend.settings import settings


_client = None
_client_error: str | None = None


def memory_filters() -> dict:
    return {
        "user_id": settings.mem0_user_id,
    }


def get_memory_client():
    global _client, _client_error

    if _client is not None:
        return _client

    if not settings.mem0_api_key:
        _client_error = "manca MEM0_API_KEY"
        return None

    try:
        _client = MemoryClient(api_key=settings.mem0_api_key)
    except Exception as exc:
        _client_error = str(exc)
        return None

    return _client


def format_memory_results(response, limit: int = 5) -> str:
    if not response:
        return "MEMORIA INTERNA: nessun contesto rilevante recuperato."

    if isinstance(response, dict):
        results = response.get("results") or response.get("memories") or []
    else:
        results = response

    if not results:
        return "MEMORIA INTERNA: nessun contesto rilevante recuperato."

    memories = []

    for item in results[:limit]:
        if isinstance(item, dict):
            memory_id = (
                item.get("id")
                or item.get("memory_id")
                or item.get("uuid")
            )
            memory = (
                item.get("memory")
                or item.get("text")
                or item.get("content")
                or str(item)
            )
            if memory_id:
                memories.append(f"[memory_id: {memory_id}] {memory}")
            else:
                memories.append(memory)
        else:
            memories.append(str(item))

    return (
        "MEMORIA INTERNA RECUPERATA.\n"
        "Usa queste note solo come contesto. Non dire 'ho trovato memorie', "
        "non mostrare un elenco grezzo e non citare questo blocco. "
        "Rispondi direttamente in modo naturale, conversazionale e sintetico.\n\n"
        "Contesto: "
        + " ".join(memories)
    )


def save_consultant_memory(content: str, category: str) -> str:
    client = get_memory_client()

    if client is None:
        reason = _client_error or "client non disponibile"
        return f"Memoria semantica disattivata: {reason}."

    try:
        client.add(
            messages=[
                {
                    "role": "user",
                    "content": f"[{category}] {content}",
                }
            ],
            user_id=settings.mem0_user_id,
        )
    except Exception as exc:
        return f"Non sono riuscito a salvare in Mem0: {exc}"

    return f"Ho salvato in memoria: {content}"


def search_consultant_memory(query: str, category: str | None = None) -> str:
    client = get_memory_client()

    if client is None:
        reason = _client_error or "client non disponibile"
        return f"Memoria semantica disattivata: {reason}."

    search_query = f"[{category}] {query}" if category else query

    try:
        response = client.search(
            query=search_query,
            filters=memory_filters(),
        )
    except Exception as exc:
        return f"Non sono riuscito a recuperare memorie da Mem0: {exc}"

    return format_memory_results(response)


def delete_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    client = get_memory_client()

    if client is None:
        reason = _client_error or "client non disponibile"
        return f"Memoria semantica disattivata: {reason}."

    normalized_memory_id = memory_id.strip()

    if not normalized_memory_id:
        return "Non posso eliminare la memoria: memory_id mancante."

    try:
        client.delete(
            memory_id=normalized_memory_id,
            delete_linked=delete_linked,
        )
    except Exception as exc:
        return f"Non sono riuscito a eliminare la memoria Mem0 {normalized_memory_id}: {exc}"

    return f"Memoria Mem0 eliminata: {normalized_memory_id}"


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
