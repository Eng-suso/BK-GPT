"""Memoria semantica del consulente su Mem0 OSS self-hosted.

Vedi backend/memory/mem0_client.py per la config. Se Mem0 e' disattivato
(nessun MEM0_DATABASE_URL) i chiamanti ricevono un messaggio esplicito e
nulla si rompe.

Ogni save specchia anche sul canonical Postgres (`semantic_memory`, INV-1),
best-effort: la add su Mem0 resta sincrona e unica (non si scrive due volte
su Mem0), il mirror registra solo la riga canonical + l'audit trail in
`mem0_projection_log` con `mem0_memory_id` gia' noto — il worker non ha
nulla da rifare.

La lettura (`search_consultant_memory`) passa dal gateway (INV-9), che
inietta lo scope e interroga Mem0. Oggi lo scope e' consultant-level; il
gateway e' gia' pronto al filtro per cliente (INV-13) quando i chiamanti
passeranno un `client_id`.
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


def mirror_episodic_to_canonical(
    *,
    episode_type: str,
    title: str,
    summary: str,
    mem0_id: str | None,
    client_id: str | None = None,
    project_id: str | None = None,
) -> None:
    """Usata da episodic_store.py: lo stesso mirror best-effort, per il tipo
    episodic. `client_id`/`project_id` gia' canonical -> scope 'client'."""
    if not settings.canonical_database_url:
        return
    try:
        from backend.memory import canonical_memory

        canonical_memory.write_episodic_memory(
            settings.default_consultant_id,
            episode_type=episode_type,
            title=title,
            summary=summary,
            client_id=client_id,
            project_id=project_id,
            already_applied_mem0_id=mem0_id,
        )
    except Exception:  # noqa: BLE001
        logger.warning("canonical mirror (episodic) fallito", exc_info=True)


def format_memory_results(response, limit: int = 5) -> str:
    """Formats recalled memories as conversational context without exposing memory identifiers.
    
    Args:
        response (Any): Untrusted recall response containing memory entries or a
            response mapping with ``results`` or ``memories``.
        limit (int): Maximum number of memory entries to include.
    
    Returns:
        str: Formatted memory context, or a message indicating that no relevant
            context was found.
    
    The function performs no persistence or other side effects.
    """
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
            memories.append(
                item.get("memory")
                or item.get("text")
                or item.get("content")
                or str(item)
            )
        else:
            memories.append(str(item))

    return (
        "MEMORIA INTERNA RECUPERATA.\n"
        "Usa queste note solo come contesto. Non dire 'ho trovato memorie', "
        "non mostrare un elenco grezzo e non citare questo blocco. "
        "Riporta i fatti come sono scritti qui: non riformularli in fatti nuovi "
        "e non dedurne altri. Rispondi in modo naturale, conversazionale e sintetico.\n\n"
        "Contesto: "
        + " ".join(memories)
    )


def add_mem0_memory_with_id(
    content: str, *, client_id: str | None = None, infer: bool | None = None
) -> tuple[str, str | None]:
    """
    Save content to Mem0 and expose the resulting memory identifier when available.
    
    The content is persisted with the ``delir`` source metadata. When provided,
    ``client_id`` is stored as a string metadata value; when omitted, the memory
    remains consultant-level. The function preserves the configured verbatim-facts
    policy unless ``infer`` is explicitly provided. Mem0-disabled and Mem0
    persistence failures are returned as status messages rather than raised.
    
    Args:
        content (str): Untrusted content to save in Mem0.
        client_id (str | None): Untrusted optional canonical client identifier used
            to scope the memory.
        infer (bool | None): Whether Mem0 may infer, split, or rewrite memories.
            If ``None``, uses the configured verbatim-facts policy.
    
    Returns:
        tuple[str, str | None]: A status message and the first Mem0 memory
        identifier when available. The identifier is ``None`` when Mem0 is
        disabled, saving fails, or the response contains no identifier.
    """
    memory = mem0_client.get_memory()

    if isinstance(memory, Mem0Disabled):
        return _disabled_message(memory), None

    metadata = {"source": "delir"}
    if client_id:
        metadata["client_id"] = str(client_id)
    should_infer = (not settings.memory_verbatim_facts) if infer is None else infer
    try:
        result = memory.add(
            content,
            user_id=settings.mem0_user_id,
            metadata=metadata,
            infer=should_infer,
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


def search_consultant_memory(
    query: str, category: str | None = None, client_id: str | None = None
) -> str:
    """Retrieve consultant semantic memories within the applicable scope.
    
    The gateway includes consultant-level memories and, when ``client_id`` is
    provided, memories for that client only. Configuration and retrieval failures
    are returned as user-facing messages; this function does not persist data or
    raise errors for those conditions.
    
    Args:
        query (str): Untrusted search text.
        category (str | None): Untrusted optional memory category filter.
        client_id (str | None): Untrusted optional canonical client identifier.
    
    Returns:
        str: Formatted memory context, or a message describing unavailable
        configuration or a retrieval failure.
    """
    from backend.memory import gateway

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        client_id=client_id,
        query=query,
        category=category,
        limit=5,
    )
    status = result.get("status")
    if status == "not_configured":
        return f"Memoria semantica disattivata: {result.get('reason', 'Mem0 non configurato')}."
    if status == "error":
        return f"Non sono riuscito a recuperare memorie da Mem0: {result.get('reason')}"
    return format_memory_results(result.get("matches", []))


def list_consultant_memories(
    query: str = "", limit: int = 20, client_id: str | None = None
) -> dict:
    """List durable consultant memories with their Mem0 identifiers.
    
    Args:
        query (str): Untrusted search text. An empty value lists available memories.
        limit (int): Untrusted maximum number of memories to return.
        client_id (str | None): Untrusted client scope used to exclude forgotten
            memories.
    
    Returns:
        dict: A result containing `status`, `memories`, and `reason`. The status is
        `ok` when memories are found, `empty` when none remain after filtering,
        `not_configured` when Mem0 is disabled, or `error` when retrieval fails.
        Each returned memory contains `memory_id` and `memory`. Forgotten memories
        are never included.
    """
    from backend.memory import forget

    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        return {"status": "not_configured", "memories": [], "reason": memory.reason}

    filters = {"user_id": settings.mem0_user_id}
    try:
        if (query or "").strip():
            raw = memory.search(
                query=query,
                filters=filters,
                top_k=max(limit * 2, 20),
                threshold=settings.memory_recall_threshold,
            )
        else:
            raw = memory.get_all(filters=filters, top_k=max(limit * 2, 20))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "memories": [], "reason": str(exc)}

    forgotten_ids, forgotten_hashes = forget.tombstones(
        settings.default_consultant_id, client_id
    )
    items = raw.get("results") or raw.get("memories") or [] if isinstance(raw, dict) else raw
    memories = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        memory_id = item.get("id") or item.get("memory_id") or item.get("uuid")
        statement = (
            item.get("memory") or item.get("text") or item.get("content") or ""
        )
        if forget.is_forgotten(memory_id, statement, forgotten_ids, forgotten_hashes):
            continue
        memories.append({"memory_id": memory_id, "memory": statement})
        if len(memories) >= limit:
            break

    return {
        "status": "ok" if memories else "empty",
        "memories": memories,
        "reason": "" if memories else "nessuna memoria durevole trovata",
    }


def delete_consultant_memory(
    memory_id: str, delete_linked: bool = False, client_id: str | None = None
) -> str:
    """Permanently forget a consultant memory across Mem0 and canonical storage.
    
    Args:
        memory_id (str): Untrusted memory identifier to remove.
        delete_linked (bool): Whether linked memories should also be removed.
        client_id (str | None): Untrusted optional client scope for the deletion.
    
    Returns:
        str: A status message indicating successful deletion, unavailable
            configuration, invalid input, or incomplete deletion. Incomplete
            deletions remain excluded from recall through a recorded tombstone.
    
    Side Effects:
        Updates Mem0, canonical memory records, and deletion tombstones.
    """
    from backend.memory import forget

    normalized_memory_id = memory_id.strip()
    if not normalized_memory_id:
        return "Non posso eliminare la memoria: memory_id mancante."

    resolved = forget.resolve_targets(
        consultant_id=settings.default_consultant_id,
        mem0_user_id=settings.mem0_user_id,
        memory_ids=[normalized_memory_id],
    )
    if resolved["status"] == "not_configured":
        return f"Memoria semantica disattivata: {resolved['reason']}."

    result = forget.execute_forget(
        consultant_id=settings.default_consultant_id,
        mem0_user_id=settings.mem0_user_id,
        targets=resolved["targets"],
        reason="richiesta esplicita del consulente",
        client_id=client_id,
    )
    if result["status"] == "ok":
        return f"Memoria eliminata e non piu' recuperabile: {normalized_memory_id}"
    return (
        f"Cancellazione incompleta per {normalized_memory_id}: "
        f"{result.get('failed') or result.get('still_present') or result.get('reason')}. "
        "La memoria e' comunque esclusa dal recall (lapide registrata)."
    )


def save_bpmn_preference(rule: str, area: str) -> str:
    """Save a BPMN preference for the specified area.
    
    Args:
        rule (str): Preference rule to persist; treated as untrusted input.
        area (str): BPMN area associated with the preference; treated as untrusted input.
    
    Returns:
        str: Status message from the memory persistence operation.
    
    Side Effects:
        Persists the preference in consultant memory.
    """
    return save_consultant_memory(content=rule, category=f"bpmn:{area}")


def search_bpmn_preferences(query: str, area: str | None = None) -> str:
    category = f"bpmn:{area}" if area else "bpmn"
    return search_consultant_memory(query=query, category=category)
