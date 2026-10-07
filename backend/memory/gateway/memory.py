"""`memory_search`: il recall Mem0 con lo scope iniettato (INV-9)."""

from __future__ import annotations

from typing import Any

from backend.memory import forget
from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.services import degradation_counters
from backend.settings import settings

# --------------------------------------------------------------------------- #
# memory_search — recall Mem0 con scope iniettato (INV-9)
# --------------------------------------------------------------------------- #


def _mem0_user_id(consultant_id: str) -> str:
    """Mem0 non ha tenant ACL: lo scope consulente e' l'`user_id`.

    Per compatibilita', il consulente MVP di default continua a leggere lo
    storico salvato sotto `settings.mem0_user_id`. Gli altri consulenti usano il
    proprio UUID come namespace, coerente con `canonical_memory`/worker.
    """
    normalized = str(consultant_id or "").strip()
    if not normalized or normalized == str(settings.default_consultant_id):
        return settings.mem0_user_id
    return normalized


def _mem0_items(raw: Any) -> list:
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("memories") or []
    return raw or []


def _memory_out_of_scope(
    metadata: dict[str, Any],
    client_id: str | None,
    project_id: str | None,
) -> bool:
    """Una memoria e' fuori scope se dichiara un'appartenenza diversa da questa.

    Le memorie senza appartenenza (preferenze, metodo, profilo del consulente)
    restano visibili ovunque: sono del consulente, non di un incarico. Quelle
    che dichiarano un cliente o un progetto valgono solo li'.
    """
    mem_client = metadata.get("client_id")
    if mem_client and str(mem_client) != (str(client_id) if client_id else None):
        return True
    mem_project = metadata.get("project_id")
    return bool(project_id and mem_project and str(mem_project) != str(project_id))


def memory_search(
    *,
    consultant_id: str,
    client_id: str | None = None,
    project_id: str | None = None,
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Searches Mem0 memories within the consultant and client scope.
    
    Consultant-level memories remain visible across client contexts, while
    client-scoped memories are returned only for the requested client. Forgotten
    memories are excluded by both identifier and content, and results are limited
    to the configured recall threshold.
    
    Args:
        consultant_id (str): Consultant namespace identifier; treated as untrusted
            input.
        client_id (str | None): Optional client scope; treated as untrusted input.
        project_id (str | None): Optional canonical project scope. When given,
            memories that declare a different project are excluded; memories with
            no project declared stay visible. Treated as untrusted input.
        query (str): Search text; treated as untrusted input.
        category (str | None): Optional category prefix for the search; treated as
            untrusted input.
        limit (int): Maximum number of matches to return; treated as untrusted
            input.
    
    Returns:
        dict[str, Any]: A result containing ``status``, ``count``, and ``matches``.
            The status is ``"ok"`` when matches are found, ``"empty"`` when none
            qualify, ``"not_configured"`` when Mem0 is unavailable, or ``"error"``
            when the search fails. Error results also include ``reason``.
    
    Raises:
        No exceptions are raised; Mem0 search failures are returned with
        ``status="error"``.
    
    This function performs read-only operations and does not persist memories.
    """
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        return {"status": "not_configured", "matches": [], "count": 0, "reason": memory.reason}

    search_query = f"[{category}] {query}" if category else (query or "")
    try:
        raw = memory.search(
            query=search_query,
            filters={"user_id": _mem0_user_id(consultant_id)},
            top_k=max(limit * 4, 20),
            threshold=settings.memory_recall_threshold,
        )
    except Exception as exc:  # noqa: BLE001 — la lettura non deve far fallire il tool
        degradation_counters.bump("memory_search", "error", detail=str(exc))
        return {"status": "error", "matches": [], "count": 0, "reason": str(exc)}

    forgotten_ids, forgotten_hashes = forget.tombstones(consultant_id, client_id)
    cid = str(client_id) if client_id else None
    matches: list[dict[str, Any]] = []
    for item in _mem0_items(raw):
        if not isinstance(item, dict):
            matches.append(
                {"memory_id": None, "memory": str(item), "score": None, "client_scoped": False}
            )
        else:
            metadata = item.get("metadata") or {}
            mem_client = metadata.get("client_id")
            if _memory_out_of_scope(metadata, cid, project_id):
                continue  # memoria di un altro cliente o di un altro incarico
            memory_id = item.get("id") or item.get("memory_id") or item.get("uuid")
            statement = (
                item.get("memory")
                or item.get("text")
                or item.get("content")
                or str(item)
            )
            if forget.is_forgotten(memory_id, statement, forgotten_ids, forgotten_hashes):
                continue  # dimenticata su richiesta: non torna, con nessun id
            matches.append(
                {
                    "memory_id": memory_id,
                    "memory": statement,
                    "score": item.get("score"),
                    "client_scoped": bool(mem_client),
                }
            )
        if len(matches) >= limit:
            break

    return {"status": "ok" if matches else "empty", "count": len(matches), "matches": matches}
