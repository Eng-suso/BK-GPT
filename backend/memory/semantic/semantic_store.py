"""Memoria semantica del consulente su Mem0 OSS self-hosted.

Vedi backend/memory/mem0_client.py per la config. Se Mem0 e' disattivato
(nessun MEM0_DATABASE_URL) i chiamanti ricevono un messaggio esplicito e
nulla si rompe.

Nota: oggi lo scope e' consultant-level (`settings.mem0_user_id`). Lo scope
per cliente/progetto arrivera' con la migrazione della memoria canonica
(piano "Cervello DeliR", INV-13).
"""

from __future__ import annotations

from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.memory.models import ConsultantSemanticMemory, semantic_memory_to_mem0_content
from backend.settings import settings


def memory_filters() -> dict:
    return {"user_id": settings.mem0_user_id}


def _disabled_message(memory: Mem0Disabled) -> str:
    return f"Memoria semantica disattivata: {memory.reason}."


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
            memory_id = item.get("id") or item.get("memory_id") or item.get("uuid")
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
    memory = mem0_client.get_memory()

    if isinstance(memory, Mem0Disabled):
        return _disabled_message(memory)

    try:
        memory.add(
            content,
            user_id=settings.mem0_user_id,
            metadata={"source": "delir"},
        )
    except Exception as exc:
        return f"Non sono riuscito a salvare in Mem0: {exc}"

    return "Memoria salvata in Mem0."


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
    memory = mem0_client.get_memory()

    if isinstance(memory, Mem0Disabled):
        return _disabled_message(memory)

    search_query = f"[{category}] {query}" if category else query

    try:
        response = memory.search(
            query=search_query,
            filters=memory_filters(),
            limit=5,
        )
    except Exception as exc:
        return f"Non sono riuscito a recuperare memorie da Mem0: {exc}"

    return format_memory_results(response)


def delete_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    memory = mem0_client.get_memory()

    if isinstance(memory, Mem0Disabled):
        return _disabled_message(memory)

    normalized_memory_id = memory_id.strip()

    if not normalized_memory_id:
        return "Non posso eliminare la memoria: memory_id mancante."

    try:
        memory.delete(memory_id=normalized_memory_id)
    except Exception as exc:
        return f"Non sono riuscito a eliminare la memoria Mem0 {normalized_memory_id}: {exc}"

    return f"Memoria Mem0 eliminata: {normalized_memory_id}"


def save_bpmn_preference(rule: str, area: str) -> str:
    return save_consultant_memory(content=rule, category=f"bpmn:{area}")


def search_bpmn_preferences(query: str, area: str | None = None) -> str:
    category = f"bpmn:{area}" if area else "bpmn"
    return search_consultant_memory(query=query, category=category)
