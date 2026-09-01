"""Memoria semantica del consulente su Mem0 OSS self-hosted.

Vedi backend/memory/mem0_client.py per la config. Se Mem0 e' disattivato
(nessun MEM0_DATABASE_URL) i chiamanti ricevono un messaggio esplicito e
nulla si rompe.

Ogni save specchia anche sul canonical Postgres (`semantic_memory`, INV-1),
best-effort: la add su Mem0 resta sincrona e unica (non si scrive due volte
su Mem0), il mirror registra solo la riga canonical + l'audit trail in
`mem0_projection_log` con `mem0_memory_id` gia' noto — il worker non ha
nulla da rifare.

Nota: oggi lo scope e' consultant-level (`settings.mem0_user_id` /
`settings.default_consultant_id`). Lo scope per cliente arrivera' col gateway
(piano "Cervello DeliR", INV-13).
"""

from __future__ import annotations

import logging

from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.memory.models import ConsultantSemanticMemory, semantic_memory_to_mem0_content
from backend.settings import settings

logger = logging.getLogger(__name__)

_KIND_BY_DURABILITY = {
    "preference": "preference",
    "method": "rule",
    "profile": "concept",
    "working_assumption": "fact",
    "stable": "fact",
}


def memory_filters() -> dict:
    return {"user_id": settings.mem0_user_id}


def _disabled_message(memory: Mem0Disabled) -> str:
    return f"Memoria semantica disattivata: {memory.reason}."


def _first_memory_id(result) -> str | None:
    if isinstance(result, dict):
        items = result.get("results") or result.get("memories") or []
        if items and isinstance(items[0], dict):
            return items[0].get("id")
    return None


def _mirror_semantic(memory: ConsultantSemanticMemory, mem0_id: str | None) -> None:
    if not settings.canonical_database_url:
        return
    try:
        from backend.memory import canonical_memory

        canonical_memory.write_semantic_memory(
            settings.default_consultant_id,
            kind=_KIND_BY_DURABILITY.get(memory.durability, "fact"),
            statement=memory.statement,
            category=memory.category,
            confidence=memory.confidence,
            already_applied_mem0_id=mem0_id,
        )
    except Exception:  # noqa: BLE001 — mai rompere il save per colpa del mirror
        logger.warning("canonical mirror (semantic) fallito", exc_info=True)


def mirror_episodic_to_canonical(*, episode_type: str, title: str, summary: str, mem0_id: str | None) -> None:
    """Usata da episodic_store.py: lo stesso mirror best-effort, per il tipo episodic."""
    if not settings.canonical_database_url:
        return
    try:
        from backend.memory import canonical_memory

        canonical_memory.write_episodic_memory(
            settings.default_consultant_id,
            episode_type=episode_type,
            title=title,
            summary=summary,
            already_applied_mem0_id=mem0_id,
        )
    except Exception:  # noqa: BLE001
        logger.warning("canonical mirror (episodic) fallito", exc_info=True)


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


def add_mem0_memory_with_id(content: str) -> tuple[str, str | None]:
    """Come add_mem0_memory, ma ritorna anche il memory_id di Mem0 (se noto) —
    serve al mirror canonical per registrare la riga gia' applicata."""
    memory = mem0_client.get_memory()

    if isinstance(memory, Mem0Disabled):
        return _disabled_message(memory), None

    try:
        result = memory.add(
            content,
            user_id=settings.mem0_user_id,
            metadata={"source": "delir"},
        )
    except Exception as exc:
        return f"Non sono riuscito a salvare in Mem0: {exc}", None

    return "Memoria salvata in Mem0.", _first_memory_id(result)


def add_mem0_memory(content: str) -> str:
    message, _ = add_mem0_memory_with_id(content)
    return message


def save_structured_consultant_memory(memory: ConsultantSemanticMemory) -> str:
    message, mem0_id = add_mem0_memory_with_id(semantic_memory_to_mem0_content(memory))

    if not message.startswith("Memoria salvata"):
        return message

    _mirror_semantic(memory, mem0_id)
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
