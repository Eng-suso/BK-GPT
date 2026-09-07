"""Dimenticare una memoria, davvero (C-MEM-02).

Prima: `forget_consultant_memory` chiamava `mem0.delete(memory_id)` e diceva
"eliminata". Tre modi in cui non lo era:

1. Mem0 con `infer=True` estrae piu' fatti da una frase: l'id restituito al
   salvataggio e' solo il primo. I fratelli restavano.
2. La riga canonical (`semantic_memory`) restava `active`, e con lei la riga
   `mem0_projection_log`: un rebuild della proiezione (INV-2, documentato) la
   riproietta identica.
3. Niente verificava l'esito. L'agente annunciava una cancellazione che poteva
   essere fallita in silenzio.

Qui la cancellazione e' una sola operazione con tre effetti e una verifica:

    lapide (memory_tombstone)  -> il recall la filtra per sempre, per id **e**
                                  per hash del testo: regge anche se Mem0
                                  riscrive lo stesso fatto sotto un id nuovo
    delete su Mem0             -> toglie il documento dall'indice
    canonical -> 'rejected'    -> la SoT smette di affermarlo, e il replay non
                                  lo resuscita

`resolve_targets` congela il bersaglio *prima* della conferma: chi conferma
esegue esattamente quei fatti, non una ricerca rifatta al turno dopo.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import text

from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.settings import settings

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def normalize_statement(value: str) -> str:
    """Canonicalize statement text for consistent comparison and hashing.
    
    Args:
        value (str): Untrusted statement text to normalize.
    
    Returns:
        str: Lowercase text with collapsed whitespace and surrounding punctuation
            removed. Empty or null-like input produces an empty string.
    """
    return _EDGE_PUNCT.sub("", _WS.sub(" ", str(value or "")).strip().lower())


def statement_hash(value: str) -> str:
    """Compute a SHA-256 hash for a normalized statement.
    
    Args:
        value (str): Untrusted statement text to normalize and hash.
    
    Returns:
        str: The lowercase hexadecimal SHA-256 digest of the normalized statement.
    """
    return hashlib.sha256(normalize_statement(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# lettura: cosa e' tombstonato (usata dal recall)
# --------------------------------------------------------------------------- #


def tombstones(
    consultant_id: str, client_id: str | None = None
) -> tuple[set[str], set[str]]:
    """
    Read forgotten memory identifiers and normalized statement hashes for a consultant.
    
    The function reads canonical tombstone data without modifying persistence. If the
    canonical database is unavailable, unconfigured, or unreadable, it returns empty
    sets so recall can continue.
    
    Args:
        consultant_id (str): Untrusted consultant identifier used to select tombstones.
        client_id (str | None): Untrusted optional client identifier used to scope the
            tombstones.
    
    Returns:
        tuple[set[str], set[str]]: A pair containing forgotten Mem0 memory IDs and
        forgotten statement hashes.
    
    """
    if not settings.canonical_database_url:
        return set(), set()

    from backend.db import canonical_session

    try:
        with canonical_session(consultant_id, client_id) as session:
            rows = session.execute(
                text("SELECT mem0_memory_id, statement_hash FROM memory_tombstone")
            ).all()
    except Exception:  # noqa: BLE001 — il recall non deve fallire per il filtro
        logger.warning("memory_tombstone non leggibile", exc_info=True)
        return set(), set()

    ids = {str(r.mem0_memory_id) for r in rows if r.mem0_memory_id}
    hashes = {str(r.statement_hash) for r in rows}
    return ids, hashes


def is_forgotten(
    memory_id: str | None,
    statement: str | None,
    forgotten_ids: set[str],
    forgotten_hashes: set[str],
) -> bool:
    """Determine whether a memory is marked as forgotten by its ID or statement hash.
    
    Args:
        memory_id: An untrusted memory identifier to compare with forgotten IDs.
        statement: An untrusted memory statement whose normalized hash is compared
            with forgotten hashes.
        forgotten_ids: Memory identifiers recorded as forgotten.
        forgotten_hashes: Normalized statement hashes recorded as forgotten.
    
    Returns:
        True if the memory ID or normalized statement hash is recorded as
        forgotten, False otherwise.
    """
    if memory_id and str(memory_id) in forgotten_ids:
        return True
    return bool(statement) and statement_hash(statement or "") in forgotten_hashes


# --------------------------------------------------------------------------- #
# risoluzione del bersaglio (prima della conferma)
# --------------------------------------------------------------------------- #


def _mem0_items(raw: Any) -> list:
    """Normalize a Mem0 response into a list of memory items.
    
    Args:
        raw (Any): Untrusted Mem0 response value, either a mapping containing
            ``results`` or ``memories`` or a list-like value.
    
    Returns:
        list: Memory items extracted from the response, or an empty list when no
            items are available.
    
    """
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("memories") or []
    return raw or []


def _item_text(item: dict) -> str:
    """Extract the memory text from a Mem0 item.
    
    Args:
        item (dict): Untrusted item containing a ``memory``, ``text``, or
            ``content`` field.
    
    Returns:
        str: The first available text value, or an empty string if none exists.
    """
    return str(
        item.get("memory") or item.get("text") or item.get("content") or ""
    )


def resolve_targets(
    *,
    consultant_id: str,
    mem0_user_id: str,
    memory_ids: list[str] | None = None,
    query: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Resolve the Mem0 memories targeted by an erasure request.
    
    Reads Mem0 without modifying persistent state. Explicit memory IDs are resolved
    exactly, while query matches are limited and filtered to the specified user.
    The returned targets are frozen as memory ID and statement pairs.
    
    Args:
        consultant_id (str): Untrusted consultant identifier associated with the request.
        mem0_user_id (str): Untrusted Mem0 user identifier used to scope query results.
        memory_ids (list[str] | None): Untrusted memory IDs to resolve exactly.
        query (str): Untrusted search text used to find additional memories.
        limit (int): Maximum number of combined targets collected through search.
    
    Returns:
        dict[str, Any]: A result containing `status`, `targets`, and `reason`.
            Status is `ok` when targets are found, `empty` when none match,
            `not_configured` when Mem0 is unavailable, or `error` when searching
            Mem0 fails. Each target contains `memory_id` and `statement`.
    """
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        return {"status": "not_configured", "targets": [], "reason": memory.reason}

    wanted_ids = [str(m).strip() for m in (memory_ids or []) if str(m).strip()]
    targets: dict[str, str] = {}

    for memory_id in wanted_ids:
        try:
            item = memory.get(memory_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("mem0.get(%s) fallita: %s", memory_id, exc)
            item = None
        targets[memory_id] = _item_text(item) if isinstance(item, dict) else ""

    if (query or "").strip():
        try:
            raw = memory.search(
                query=query,
                filters={"user_id": mem0_user_id},
                top_k=max(limit * 2, 20),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "targets": [], "reason": str(exc)}

        for item in _mem0_items(raw):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id") or item.get("memory_id") or item.get("uuid")
            if not item_id or str(item_id) in targets:
                continue
            targets[str(item_id)] = _item_text(item)
            if len(targets) >= limit:
                break

    resolved = [
        {"memory_id": memory_id, "statement": statement}
        for memory_id, statement in targets.items()
    ]
    return {
        "status": "ok" if resolved else "empty",
        "targets": resolved,
        "reason": "" if resolved else "nessuna memoria corrisponde alla richiesta",
    }


# --------------------------------------------------------------------------- #
# esecuzione
# --------------------------------------------------------------------------- #


def _write_tombstones(
    consultant_id: str,
    client_id: str | None,
    targets: list[dict[str, Any]],
    reason: str,
) -> int:
    """
    Persist tombstones for the specified memory targets.
    
    The operation is idempotent: existing tombstones are preserved without
    creating duplicates. If the canonical database is not configured, no
    persistence is performed and the function returns zero. Database changes are
    committed by the canonical session context.
    
    Args:
        consultant_id (str): Consultant identifier.
        client_id (str | None): Optional client identifier.
        targets (list[dict[str, Any]]): Untrusted memory target records. Each
            record may provide ``memory_id`` and ``statement``.
        reason (str): Untrusted explanation associated with the tombstones.
    
    Returns:
        int: Number of target tombstone insertions attempted.
    """
    if not settings.canonical_database_url:
        return 0

    from backend.db import canonical_session

    written = 0
    with canonical_session(consultant_id, client_id) as session:
        for target in targets:
            statement = str(target.get("statement") or "")
            session.execute(
                text(
                    "INSERT INTO memory_tombstone "
                    "(consultant_id, client_id, mem0_memory_id, statement_hash, "
                    " statement, reason) "
                    "VALUES (:c, :cl, :mid, :h, :st, :r) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "c": str(consultant_id),
                    "cl": str(client_id) if client_id else None,
                    "mid": target.get("memory_id") or None,
                    "h": statement_hash(statement),
                    "st": statement,
                    "r": reason or None,
                },
            )
            written += 1
    return written


def _reject_canonical_rows(
    consultant_id: str, client_id: str | None, targets: list[dict[str, Any]]
) -> int:
    """Marks matching active canonical memory rows as rejected.
    
    Matching is based on normalized statements, and already rejected rows remain
    unchanged. The update is persisted in the canonical database. If the canonical
    database is not configured or no target statements are provided, no rows are
    changed.
    
    Args:
        consultant_id (str): Consultant identifier.
        client_id (str | None): [Untrusted input] Optional client identifier.
        targets (list[dict[str, Any]]): [Untrusted input] Memory targets whose
            statements identify canonical rows to reject.
    
    Returns:
        int: Number of canonical rows updated.
    """
    wanted = {
        normalize_statement(str(t.get("statement") or ""))
        for t in targets
        if str(t.get("statement") or "").strip()
    }
    if not wanted or not settings.canonical_database_url:
        return 0

    from backend.db import canonical_session

    with canonical_session(consultant_id, client_id) as session:
        rows = session.execute(
            text("SELECT id, statement FROM semantic_memory WHERE status <> 'rejected'")
        ).all()
        matched = [
            str(row.id) for row in rows if normalize_statement(row.statement) in wanted
        ]
        if not matched:
            return 0
        session.execute(
            text(
                "UPDATE semantic_memory SET status = 'rejected' "
                "WHERE id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": matched},
        )
        return len(matched)


def execute_forget(
    *,
    consultant_id: str,
    mem0_user_id: str,
    targets: list[dict[str, Any]],
    reason: str = "",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Persist forget markers, reject matching canonical memories, and delete and verify the targets in Mem0.
    
    The tombstones and canonical rejections are written before Mem0 deletion so failed
    deletions remain excluded from recall. A successful result requires every target
    deletion to complete and every deleted memory to be absent during verification.
    This function performs persistent database updates and Mem0 mutations.
    
    Args:
        consultant_id (str): Consultant identifier.
        mem0_user_id (str): Mem0 user identifier.
        targets (list[dict[str, Any]]): Untrusted, frozen memory targets to forget.
        reason (str): Untrusted explanation recorded with the tombstones.
        client_id (str | None): Optional untrusted client identifier used for
            tenant-scoped persistence.
    
    Returns:
        dict[str, Any]: Outcome containing the status, deleted and failed memory
        identifiers, memories still present after verification, and counts of
        tombstones and canonical rows updated. The status is `empty` when no targets
        are supplied, `ok` when all deletions are verified, or `partial` when Mem0
        is disabled, a deletion fails, or a deleted memory remains present.
    """
    if not targets:
        return {
            "status": "empty",
            "deleted": [],
            "failed": [],
            "still_present": [],
            "tombstoned": 0,
            "canonical_rejected": 0,
        }

    tombstoned = _write_tombstones(consultant_id, client_id, targets, reason)
    canonical_rejected = _reject_canonical_rows(consultant_id, client_id, targets)

    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        return {
            "status": "partial",
            "deleted": [],
            "failed": [t.get("memory_id") for t in targets],
            "still_present": [],
            "tombstoned": tombstoned,
            "canonical_rejected": canonical_rejected,
            "reason": memory.reason,
        }

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for target in targets:
        memory_id = str(target.get("memory_id") or "").strip()
        if not memory_id:
            continue
        try:
            memory.delete(memory_id=memory_id)
            deleted.append(memory_id)
        except Exception as exc:  # noqa: BLE001
            failed.append({"memory_id": memory_id, "error": str(exc)})

    # verifica: quello che diciamo eliminato deve essere sparito davvero
    still_present: list[str] = []
    for memory_id in deleted:
        try:
            if memory.get(memory_id):
                still_present.append(memory_id)
        except Exception:  # noqa: BLE001 — assente = get solleva: e' l'esito atteso
            continue

    if failed or still_present:
        status = "partial"
    else:
        status = "ok"

    return {
        "status": status,
        "deleted": deleted,
        "failed": failed,
        "still_present": still_present,
        "tombstoned": tombstoned,
        "canonical_rejected": canonical_rejected,
    }
