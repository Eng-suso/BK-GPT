"""Worker che drena mem0_projection_log e applica a Mem0 OSS (INV-2).

Gira come delir_worker (`canonical_worker_url`): SELECT/UPDATE solo sulle due
code. Il payload e' gia' completo. Rebuild di Mem0 = reset dello scope +
replay di questa log in ordine di id.

Uso:
    from backend.workers.mem0_worker import drain_once, run_forever
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from sqlalchemy import create_engine, text

from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.settings import settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5


@lru_cache(maxsize=1)
def _engine():
    if not settings.canonical_worker_url:
        raise RuntimeError("canonical_worker_url non configurata (ruolo delir_worker).")
    return create_engine(settings.canonical_worker_url, future=True, pool_pre_ping=True)


def _first_memory_id(result) -> str | None:
    if isinstance(result, dict):
        items = result.get("results") or result.get("memories") or []
        if items and isinstance(items[0], dict):
            return items[0].get("id")
    return None


def _apply(memory, op: str, payload: dict) -> str | None:
    if op == "add":
        return _first_memory_id(
            memory.add(
                payload["text"],
                user_id=payload["user_id"],
                metadata=payload.get("metadata"),
            )
        )
    if op == "update":
        mid = payload.get("mem0_memory_id")
        if mid:
            memory.update(memory_id=mid, data=payload["text"])
        return mid
    if op == "delete":
        mid = payload.get("mem0_memory_id")
        if mid:
            memory.delete(memory_id=mid)
        return mid
    raise ValueError(f"op mem0_projection_log non riconosciuta: {op!r}")


def drain_once(limit: int = 200) -> int:
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        logger.warning("Mem0 non configurato: mem0_worker non fa nulla (%s).", memory.reason)
        return 0

    done = 0
    with _engine().begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, op, mem0_payload FROM mem0_projection_log "
                "WHERE applied_at IS NULL AND attempts < :maxa "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim"
            ),
            {"maxa": _MAX_ATTEMPTS, "lim": limit},
        ).all()

        for row in rows:
            try:
                mem0_id = _apply(memory, row.op, row.mem0_payload)
                conn.execute(
                    text(
                        "UPDATE mem0_projection_log "
                        "SET applied_at = now(), mem0_memory_id = COALESCE(:mid, mem0_memory_id) "
                        "WHERE id = :id"
                    ),
                    {"mid": mem0_id, "id": row.id},
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("mem0_projection_log %s fallita", row.id)
                conn.execute(
                    text(
                        "UPDATE mem0_projection_log "
                        "SET attempts = attempts + 1, last_error = :e WHERE id = :id"
                    ),
                    {"e": str(exc)[:2000], "id": row.id},
                )
    return done


def prune(older_than_days: int = 14) -> int:
    """Cancella le righe gia' applicate piu' vecchie di N giorni. Ritorna
    quante ne ha tolte."""
    with _engine().begin() as conn:
        return conn.execute(
            text(
                "DELETE FROM mem0_projection_log "
                "WHERE applied_at IS NOT NULL "
                "  AND applied_at < now() - make_interval(days => :d)"
            ),
            {"d": older_than_days},
        ).rowcount


def queue_stats() -> dict[str, int]:
    """`pending` = da applicare, `stuck` = falliti troppe volte (dead-letter)."""
    with _engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT "
                "  count(*) FILTER (WHERE applied_at IS NULL AND attempts < :m) AS pending, "
                "  count(*) FILTER (WHERE applied_at IS NULL AND attempts >= :m) AS stuck "
                "FROM mem0_projection_log"
            ),
            {"m": _MAX_ATTEMPTS},
        ).one()
    return {"pending": int(row.pending), "stuck": int(row.stuck)}


def run_forever(idle_sleep: float = 3.0) -> None:
    logger.info("mem0_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("mem0_worker: passata fallita")
            processed = 0
        time.sleep(0.0 if processed else idle_sleep)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
