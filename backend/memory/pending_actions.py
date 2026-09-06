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
    return datetime.now(timezone.utc)


def _durable() -> bool:
    return bool(settings.canonical_database_url)


def _row_to_action(row: Any) -> dict[str, Any]:
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
    """Registra un'azione in attesa. Supersede quella eventualmente aperta sul
    thread: l'ultima proposta e' l'unica confermabile."""
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
    """L'azione ancora in attesa su questo thread, o None. Una scaduta viene
    chiusa come `expired` e non ritorna: meglio ripetere la proposta che
    eseguire una conferma vecchia di ore."""
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
    """Transizione condizionata pending -> status. None se non c'era nulla da
    chiudere (gia' eseguita, annullata, scaduta o mai proposta)."""
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
    """Prende in carico l'azione in attesa (pending -> confirmed) e la ritorna.

    Atomica: il chiamante che riceve la riga e' l'unico autorizzato a eseguirla.
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
    """Esito dell'esecuzione, per audit. Best-effort: l'azione e' gia' avvenuta."""
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
    """Solo per i test del fallback in-process."""
    with _MEMORY_LOCK:
        _MEMORY_STORE.clear()
