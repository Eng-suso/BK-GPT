from backend.memory.models import ConsultantSemanticMemory, semantic_memory_to_mem0_content
from backend.memory import mem0_mcp_client
from backend.settings import settings


def memory_filters() -> dict:
    return {
        "AND": [
            {
                "user_id": settings.mem0_user_id,
            }
        ],
    }


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


def add_mem0_memory(content: str) -> str:
    try:
        result = mem0_mcp_client.add_memory(
            text=content,
            user_id=settings.mem0_user_id,
            metadata={"source": "delir"},
        )
    except Exception as exc:
        return f"Non sono riuscito a salvare in Mem0 MCP: {exc}"

    event_id = ""
    if isinstance(result, dict) and result.get("event_id"):
        event_id = f" [event_id: {result['event_id']}]"

    return f"Memoria salvata in Mem0 MCP.{event_id}"


def save_structured_consultant_memory(memory: ConsultantSemanticMemory) -> str:
    result = add_mem0_memory(semantic_memory_to_mem0_content(memory))

    if not result.startswith("Memoria salvata"):
        return result

    return f"Ho salvato in memoria: {memory.statement}"


def save_consultant_memory(content: str, category: str) -> str:
    memory = ConsultantSemanticMemory(
        category=category,
        statement=content,
        source="chat",
    )
    return save_structured_consultant_memory(memory)


def search_consultant_memory(query: str, category: str | None = None) -> str:
    search_query = f"[{category}] {query}" if category else query

    try:
        response = mem0_mcp_client.search_memories(
            query=search_query,
            filters=memory_filters(),
            limit=5,
        )
    except Exception as exc:
        return f"Non sono riuscito a recuperare memorie da Mem0 MCP: {exc}"

    return format_memory_results(response)


def delete_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    normalized_memory_id = memory_id.strip()

    if not normalized_memory_id:
        return "Non posso eliminare la memoria: memory_id mancante."

    try:
        mem0_mcp_client.delete_memory(
            memory_id=normalized_memory_id,
        )
    except Exception as exc:
        return f"Non sono riuscito a eliminare la memoria Mem0 MCP {normalized_memory_id}: {exc}"

    linked_note = " I link esterni non sono gestiti da questo tool MCP." if delete_linked else ""
    return f"Memoria Mem0 MCP eliminata: {normalized_memory_id}.{linked_note}"


def get_mem0_memories(filters: dict | None = None, page: int = 1, limit: int = 20):
    return mem0_mcp_client.get_memories(
        filters=filters or memory_filters(),
        page=page,
        limit=limit,
    )


def get_mem0_memory(memory_id: str):
    return mem0_mcp_client.get_memory(memory_id=memory_id.strip())


def update_mem0_memory(memory_id: str, text: str | None = None, metadata: dict | None = None):
    return mem0_mcp_client.update_memory(
        memory_id=memory_id.strip(),
        text=text,
        metadata=metadata,
    )


def delete_all_mem0_memories(filters: dict | None = None):
    return mem0_mcp_client.delete_all_memories(filters=filters or memory_filters())


def delete_mem0_entities(entity_type: str, entity_id: str):
    return mem0_mcp_client.delete_entities(
        entity_type=entity_type.strip(),
        entity_id=entity_id.strip(),
    )


def list_mem0_entities(entity_type: str | None = None, page: int = 1, limit: int = 50):
    return mem0_mcp_client.list_entities(
        entity_type=entity_type,
        page=page,
        limit=limit,
    )


def list_mem0_events(filters: dict | None = None, page: int = 1, limit: int = 50):
    return mem0_mcp_client.list_events(
        filters=filters or memory_filters(),
        page=page,
        limit=limit,
    )


def get_mem0_event_status(event_id: str):
    return mem0_mcp_client.get_event_status(event_id=event_id.strip())


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
