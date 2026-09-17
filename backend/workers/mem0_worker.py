"""Worker che drena mem0_projection_log e applica a Mem0 OSS (INV-2).

Gira come delir_worker (`canonical_worker_url`): SELECT/UPDATE solo sulle due
code. Il payload e' gia' completo. Rebuild di Mem0 = reset dello scope +
replay di questa log in ordine di id.

`memory.add()` fa passare il testo da un LLM: quando la coda si sveglia con
qualche centinaio di righe arretrate, il modello risponde 429 e prima ogni
fallimento consumava un tentativo. Cinque 429 in dieci secondi e la memoria
del consulente finiva in dead-letter per un limite di banda, non per un
difetto del dato. Qui un rate limit non consuma il budget dei tentativi:
sposta soltanto `next_attempt_at`, onorando l'attesa che il provider dichiara
(`Retry-After`, "try again in ...") quando la dichiara.

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
from backend.workers import retry

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5

# Quando il provider rifiuta per banda o per credito, il rifiuto vale per tutta
# la coda, non per la riga che l'ha preso: fino a qui non si sonda di nuovo.
# Senza, ogni passata (una ogni pochi secondi) prendeva la riga dovuta successiva
# e raccoglieva lo stesso 429, facendo salire il contatore di banda di tutta la
# coda fino al dead-letter.
_paused_until = 0.0


class UnsupportedMem0Op(ValueError):
    """La riga chiede un'operazione che questo worker non sa fare: non e' un
    guasto momentaneo, e riprovarla cinque volte non la rende eseguibile."""


_RESCHEDULE = text(
    "UPDATE mem0_projection_log SET "
    "  attempts = CASE WHEN :permanent THEN :maxa ELSE attempts + :spend END, "
    "  throttled_count = throttled_count + :throttle, "
    "  last_error = :e, "
    "  next_attempt_at = now() + make_interval(secs => :delay) "
    "WHERE id = :id"
)


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
    raise UnsupportedMem0Op(f"op mem0_projection_log non riconosciuta: {op!r}")


def drain_once(limit: int = 200) -> int:
    global _paused_until
    if time.monotonic() < _paused_until:
        return 0
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        logger.warning("Mem0 non configurato: mem0_worker non fa nulla (%s).", memory.reason)
        return 0

    done = 0
    with _engine().begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, op, mem0_payload, attempts, throttled_count "
                "FROM mem0_projection_log "
                "WHERE applied_at IS NULL AND attempts < :maxa "
                "  AND next_attempt_at <= now() "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim"
            ),
            {"maxa": _MAX_ATTEMPTS, "lim": limit},
        ).all()

        for row in rows:
            # Un savepoint per riga: `memory.add()` ha gia' scritto su Mem0
            # quando arriviamo all'UPDATE, quindi un errore piu' avanti nella
            # passata non deve far perdere l'`applied_at` di chi e' passato —
            # sarebbe una riproiezione dello stesso fatto.
            savepoint = conn.begin_nested()
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
                savepoint.commit()
                done += 1
            except Exception as exc:  # noqa: BLE001
                savepoint.rollback()
                failure = _reschedule(conn, row, exc)
                if failure.kind in ("throttled", "exhausted"):
                    _paused_until = time.monotonic() + failure.delay_seconds
                    # Il provider ci ha appena detto "non ora" o "non piu'":
                    # continuare il batch significa raccogliere lo stesso 429 su
                    # ogni riga rimasta. Si smette qui e la coda resta ferma
                    # per l'attesa decisa, invece di ripartire fra pochi secondi.
                    logger.warning(
                        "mem0_projection_log: %s, passata interrotta a %d righe applicate, "
                        "coda in pausa per %.0fs",
                        "credito esaurito" if failure.kind == "exhausted" else "rate limit",
                        done,
                        failure.delay_seconds,
                    )
                    break
    return done


def _reschedule(conn, row, exc: Exception) -> retry.Failure:
    """Rimette in coda la riga fallita: quando riprovarla, e se conta come tentativo."""
    failure = retry.classify(
        exc,
        attempts=int(row.attempts),
        throttled=int(getattr(row, "throttled_count", 0) or 0),
        permanent=(UnsupportedMem0Op, KeyError),
    )
    if failure.is_permanent:
        logger.error(
            "mem0_projection_log %s: riga non applicabile, dead-letter immediato (%s)",
            row.id, exc,
        )
    elif failure.kind == "exhausted":
        logger.error(
            "mem0_projection_log %s: credito o quota del provider esauriti, coda in pausa "
            "per %.0fs (tentativo non consumato): %s",
            row.id, failure.delay_seconds, exc,
        )
    elif failure.kind == "throttled":
        # Nessuno stacktrace: e' banda, non un difetto. Va visto, non indagato.
        logger.warning(
            "mem0_projection_log %s: rate limit, riprovo fra %.1fs (tentativo non consumato)",
            row.id, failure.delay_seconds,
        )
    else:
        logger.warning(
            "mem0_projection_log %s fallita, riprovo fra %.1fs",
            row.id, failure.delay_seconds, exc_info=True,
        )
    savepoint = conn.begin_nested()
    try:
        conn.execute(
            _RESCHEDULE,
            {
                "permanent": failure.is_permanent,
                "maxa": _MAX_ATTEMPTS,
                "spend": 1 if failure.consumes_attempt else 0,
                "throttle": 1 if failure.kind == "throttled" else 0,
                "e": f"{'PERMANENTE: ' if failure.is_permanent else ''}{exc}"[:2000],
                "delay": failure.delay_seconds,
                "id": row.id,
            },
        )
        savepoint.commit()
    except Exception:  # noqa: BLE001 — nemmeno la contabilita' ferma la coda
        savepoint.rollback()
        logger.exception("mem0_projection_log %s: esito non registrato", row.id)
    return failure


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
