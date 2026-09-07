"""Azioni in attesa di conferma, con stato durevole (non ricostruito dall'LLM).

Il difetto che questo modulo chiude: per un'azione distruttiva l'agente
proponeva ("elimino questa memoria?"), l'utente confermava ("si'"), e al turno
dopo il modello doveva **ricostruire semanticamente** che cosa stesse
confermando. Se il riferimento non sopravviveva al turno, la conferma cadeva nel
vuoto — o, peggio, ripartiva chiedendo di nuovo il contesto.

Qui la conferma e' legata al comando:

    propose(...)  -> congela bersaglio + anteprima in `pending_action`
    open_action() -> il turno dopo la ritrova dal thread, non dal testo
    confirm()/cancel() -> esegue o annulla *quella* riga, atomicamente

`confirm` fa una transizione condizionata (`WHERE status = 'pending'`): due
conferme concorrenti non possono eseguire due volte la stessa azione.

Backend: Postgres canonical quando configurato (RLS per consulente); altrimenti
un fallback in-process, cosi' il flusso resta deterministico anche in dev/CI
senza DB. Il fallback non sopravvive al restart: e' esattamente la garanzia che
serve a un'azione con TTL di minuti.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from backend.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 1800

_MEMORY_STORE: dict[tuple[str, str], dict[str, Any]] = {}
_MEMORY_LOCK = threading.Lock()


def _now() -> datetime:
    """Get the current time as a timezone-aware UTC datetime.
    
    Returns:
        datetime: The current UTC time with timezone information.
    """
    return datetime.now(timezone.utc)


def _durable() -> bool:
    """Determine whether durable database persistence is configured.
    
    Returns:
        bool: `True` if a canonical database URL is configured, `False` otherwise.
    """
    return bool(settings.canonical_database_url)


def _row_to_action(row: Any) -> dict[str, Any]:
    """
    Convert a persistence-layer row into the public action representation.
    
    Args:
        row (Any): Untrusted persistence-layer row containing action fields. Its
            serialized parameters, when provided as a string, must contain valid
            JSON.
    
    Returns:
        dict[str, Any]: Action data with a string identifier, normalized parameters,
            and ISO 8601 timestamps. Missing parameters become an empty dictionary,
            and missing timestamps become None.
    
    Raises:
        ValueError: If string-valued parameters contain invalid JSON.
    
    This function does not modify the row or perform persistence.
    """
    params = row.params
    if isinstance(params, str):
        params = json.loads(params)
    return {
        "id": str(row.id),
        "thread_id": row.thread_id,
        "action": row.action,
        "params": params or {},
        "preview": row.preview,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def propose(
    *,
    consultant_id: str,
    thread_id: str,
    action: str,
    params: dict[str, Any],
    preview: str,
    client_id: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """Register a pending action for a thread and persist its confirmation state.
    
    A newer proposal supersedes any existing pending action for the same thread, leaving
    only the new proposal confirmable. The action receives a pending status and an
    expiration time of at least 60 seconds. Persistence uses the configured durable
    store or the thread-safe in-memory fallback.
    
    Args:
        consultant_id: Untrusted consultant identifier used to scope the action.
        thread_id: Untrusted thread identifier associated with the action.
        action: Untrusted action type or name.
        params: Untrusted parameters captured for the proposed action.
        preview: Untrusted human-readable preview of the proposed action.
        client_id: Untrusted optional client identifier for persistence scoping.
        ttl_seconds: Requested lifetime in seconds; values below 60 are raised to 60.
    
    Returns:
        A dictionary containing the created action, including its identifier, pending
        status, timestamps, parameters, and preview.
    
    Side Effects:
        Persists the action and marks previously pending actions for the thread as
        superseded.
    """
    expires_at = _now() + timedelta(seconds=max(60, ttl_seconds))

    if not _durable():
        record = {
            "id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "action": action,
            "params": params,
            "preview": preview,
            "status": "pending",
            "created_at": _now().isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        with _MEMORY_LOCK:
            _MEMORY_STORE[(str(consultant_id), str(thread_id))] = record
        return dict(record)

    from backend.db import canonical_session

    with canonical_session(consultant_id, client_id) as session:
        session.execute(
            text(
                "UPDATE pending_action SET status = 'superseded', resolved_at = now() "
                "WHERE thread_id = :t AND status = 'pending'"
            ),
            {"t": str(thread_id)},
        )
        row = session.execute(
            text(
                "INSERT INTO pending_action "
                "(consultant_id, client_id, thread_id, action, params, preview, expires_at) "
                "VALUES (:c, :cl, :t, :a, CAST(:p AS jsonb), :prev, :exp) "
                "RETURNING id, thread_id, action, params, preview, status, "
                "          created_at, expires_at"
            ),
            {
                "c": str(consultant_id),
                "cl": str(client_id) if client_id else None,
                "t": str(thread_id),
                "a": action,
                "p": json.dumps(params, default=str),
                "prev": preview,
                "exp": expires_at,
            },
        ).one()
        return _row_to_action(row)


def open_action(
    *,
    consultant_id: str,
    thread_id: str,
    client_id: str | None = None,
    action: str | None = None,
) -> dict[str, Any] | None:
    """Find the current pending action for a thread.
    
    Expired pending actions are marked as ``expired`` and are not returned. The
    result is limited to pending actions belonging to the specified thread and,
    when provided, matching the requested action type. Access is evaluated for
    the specified consultant and client, and the action record is persisted when
    the durable store is configured.
    
    Args:
        consultant_id (str): Untrusted consultant identifier used for access
            evaluation.
        thread_id (str): Untrusted thread identifier used to scope the action.
        client_id (str | None): Untrusted client identifier used for access
            evaluation.
        action (str | None): Untrusted optional action type used to filter the
            result.
    
    Returns:
        dict[str, Any] | None: The latest matching pending action, or ``None`` if
        no matching action is available.
    """
    if not _durable():
        with _MEMORY_LOCK:
            record = _MEMORY_STORE.get((str(consultant_id), str(thread_id)))
            if record is None or record["status"] != "pending":
                return None
            if datetime.fromisoformat(record["expires_at"]) <= _now():
                record["status"] = "expired"
                return None
            if action and record["action"] != action:
                return None
            return dict(record)

    from backend.db import canonical_session

    with canonical_session(consultant_id, client_id) as session:
        session.execute(
            text(
                "UPDATE pending_action SET status = 'expired', resolved_at = now() "
                "WHERE thread_id = :t AND status = 'pending' AND expires_at <= now()"
            ),
            {"t": str(thread_id)},
        )
        row = session.execute(
            text(
                "SELECT id, thread_id, action, params, preview, status, "
                "       created_at, expires_at "
                "FROM pending_action "
                # i CAST espliciti servono a Postgres per tipizzare i parametri
                # in un confronto con NULL (AmbiguousParameter senza)
                "WHERE thread_id = :t AND status = 'pending' "
                "  AND (CAST(:a AS text) IS NULL OR action = CAST(:a AS text)) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"t": str(thread_id), "a": action},
        ).first()
        return _row_to_action(row) if row else None


def _close(
    *,
    consultant_id: str,
    thread_id: str,
    status: str,
    client_id: str | None,
    result: dict[str, Any] | None,
    action_id: str | None,
) -> dict[str, Any] | None:
    """Atomically close a pending action with a terminal status.
    
    The transition succeeds only for an unexpired pending action and, when provided,
    the specified action identifier. On success, it records the status and result and
    persists the change when durable storage is configured. Expired, already closed,
    missing, or mismatched actions remain unchanged.
    
    Args:
        consultant_id: Untrusted consultant identifier used for storage access.
        thread_id: Untrusted thread identifier that scopes the action.
        status: Terminal status to assign to the action.
        client_id: Untrusted client identifier used for storage access.
        result: Execution result to associate with the action.
        action_id: Untrusted optional action identifier used to select the action.
    
    Returns:
        The closed action record, or `None` when no eligible pending action exists.
    """
    if not _durable():
        with _MEMORY_LOCK:
            record = _MEMORY_STORE.get((str(consultant_id), str(thread_id)))
            if record is None or record["status"] != "pending":
                return None
            if action_id and record["id"] != action_id:
                return None
            if datetime.fromisoformat(record["expires_at"]) <= _now():
                record["status"] = "expired"
                return None
            record["status"] = status
            record["result"] = result
            return dict(record)

    from backend.db import canonical_session

    with canonical_session(consultant_id, client_id) as session:
        row = session.execute(
            text(
                "UPDATE pending_action SET status = :s, resolved_at = now(), "
                "       result = CAST(:r AS jsonb) "
                "WHERE thread_id = :t AND status = 'pending' AND expires_at > now() "
                "  AND (CAST(:aid AS uuid) IS NULL OR id = CAST(:aid AS uuid)) "
                "RETURNING id, thread_id, action, params, preview, status, "
                "          created_at, expires_at"
            ),
            {
                "s": status,
                "t": str(thread_id),
                "r": json.dumps(result, default=str) if result is not None else None,
                "aid": action_id,
            },
        ).first()
        return _row_to_action(row) if row else None


def claim(
    *,
    consultant_id: str,
    thread_id: str,
    client_id: str | None = None,
    action_id: str | None = None,
) -> dict[str, Any] | None:
    """Atomically claims a pending action for execution.
    
    Transitions the matching action from ``pending`` to ``confirmed`` and
    persists the transition. Only the caller that successfully claims the action
    receives it; unavailable, expired, or already transitioned actions yield
    ``None``.
    
    Args:
        consultant_id (str): Untrusted consultant identifier used to scope the
            action.
        thread_id (str): Untrusted thread identifier used to scope the action.
        client_id (str | None): Untrusted optional client identifier used to
            restrict the action.
        action_id (str | None): Untrusted optional action identifier used to select
            a specific pending action.
    
    Returns:
        dict[str, Any] | None: The claimed action, or ``None`` when no matching
        unexpired pending action is available.
    """
    return _close(
        consultant_id=consultant_id,
        thread_id=thread_id,
        status="confirmed",
        client_id=client_id,
        result=None,
        action_id=action_id,
    )


def cancel(
    *,
    consultant_id: str,
    thread_id: str,
    client_id: str | None = None,
    action_id: str | None = None,
) -> dict[str, Any] | None:
    """Cancel the pending action associated with a thread.
    
    The transition succeeds only for an available pending action belonging to the
    specified consultant and thread. The action is persisted with a ``cancelled``
    status when storage is configured.
    
    Args:
        consultant_id: Untrusted consultant identifier.
        thread_id: Untrusted thread identifier.
        client_id: Untrusted client identifier used to scope the action, if provided.
        action_id: Untrusted action identifier used to select a specific action, if provided.
    
    Returns:
        The cancelled action, or ``None`` if no matching pending action is available.
    """
    return _close(
        consultant_id=consultant_id,
        thread_id=thread_id,
        status="cancelled",
        client_id=client_id,
        result=None,
        action_id=action_id,
    )


def record_result(
    *,
    consultant_id: str,
    thread_id: str,
    action_id: str,
    result: dict[str, Any],
    client_id: str | None = None,
) -> None:
    """Record an execution result for audit without affecting the completed action.
    
    Persistence is best-effort: database errors are logged and suppressed. In-memory
    storage is updated only when the action identifier matches the current action for
    the specified thread.
    
    Args:
        consultant_id (str): Untrusted consultant identifier.
        thread_id (str): Untrusted thread identifier.
        action_id (str): Untrusted action identifier.
        result (dict[str, Any]): Untrusted execution result to persist.
        client_id (str | None): Untrusted client identifier, if applicable.
    
    Side Effects:
        Persists the result for the specified action when durable storage is
        configured.
    """
    if not _durable():
        with _MEMORY_LOCK:
            record = _MEMORY_STORE.get((str(consultant_id), str(thread_id)))
            if record is not None and record["id"] == action_id:
                record["result"] = result
        return

    from backend.db import canonical_session

    try:
        with canonical_session(consultant_id, client_id) as session:
            session.execute(
                text(
                    "UPDATE pending_action SET result = CAST(:r AS jsonb) "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"r": json.dumps(result, default=str), "id": action_id},
            )
    except Exception:  # noqa: BLE001 — l'audit non deve rompere il turno
        logger.warning("pending_action: risultato non registrato", exc_info=True)


def reset_memory_store() -> None:
    """Clear all actions from the in-process fallback store.
    
    This test-only helper removes every stored action and does not affect
    PostgreSQL persistence.
    """
    with _MEMORY_LOCK:
        _MEMORY_STORE.clear()
