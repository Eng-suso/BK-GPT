"""Worker che drena graph_outbox e proietta su Neo4j (INV-7).

Gira come ruolo delir_worker (`canonical_worker_url`): SELECT/UPDATE solo sulle
due code, nessun accesso alle tabelle di dominio. Il payload e' gia' completo,
il worker non rilegge Postgres.

MVP: worker singolo, ordine globale per `id`. L'ordinamento per-aggregate resta
un refinement di P5/P8.

Un fallimento ha due nature diverse e qui restano distinte. Un payload che il
projector non sa applicare non migliorera' riprovando (`InvalidGraphPayload`):
esce subito dalla coda e finisce in `graph_outbox_dead_letter`, intero e con il
motivo. Neo4j irraggiungibile, invece, e' momentaneo: la riga torna eleggibile
piu' tardi (`next_attempt_at`, backoff esponenziale con jitter) invece che due
secondi dopo.

Ogni riga ha il suo savepoint: il guasto di una non deve annullare le proiezioni
che le altre hanno gia' fatto nella stessa passata.

Uso:
    from backend.workers.graph_worker import drain_once, run_forever
    drain_once()          # una passata
    run_forever()         # loop (Ctrl-C per fermare)
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from sqlalchemy import create_engine, text

from backend.memory.knowledge_graph import neo4j_store, projector
from backend.memory.knowledge_graph.projector import InvalidGraphPayload
from backend.settings import settings
from backend.workers import retry

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5

_RESCHEDULE = text(
    "UPDATE graph_outbox SET "
    "  attempts = attempts + :spend, "
    "  throttled_count = throttled_count + :throttle, "
    "  last_error = :e, "
    "  next_attempt_at = now() + make_interval(secs => :delay) "
    "WHERE id = :id"
)

# Il veleno si sposta, non si annota: il CHECK della 0017 rivaluta la riga a ogni
# UPDATE, quindi annotare "non applicabile" su una riga gia' non applicabile
# solleva una CheckViolation, e in una passata a transazione unica quella riga
# bloccherebbe tutta la coda. Qui esce da `graph_outbox` e resta intera nel
# dead-letter, con il motivo, per essere diagnosticata.
_DEAD_LETTER = text(
    "INSERT INTO graph_outbox_dead_letter "
    "(id, aggregate_type, aggregate_id, consultant_id, client_id, op, payload, "
    " dedupe_key, created_at, attempts, last_error, reason) "
    "SELECT id, aggregate_type, aggregate_id, consultant_id, client_id, op, payload, "
    "       dedupe_key, created_at, attempts, last_error, :reason "
    "FROM graph_outbox WHERE id = :id "
    "ON CONFLICT (id) DO NOTHING"
)
_DROP_FROM_QUEUE = text("DELETE FROM graph_outbox WHERE id = :id")


@lru_cache(maxsize=1)
def _engine():
    if not settings.canonical_worker_url:
        raise RuntimeError(
            "canonical_worker_url non configurata (DSN del ruolo delir_worker)."
        )
    return create_engine(settings.canonical_worker_url, future=True, pool_pre_ping=True)


def drain_once(limit: int = 200) -> int:
    """Processa fino a `limit` righe pendenti. Ritorna quante ne ha completate."""
    driver = neo4j_store.get_driver()
    if driver is None:
        logger.warning("Neo4j non configurato: graph_worker non fa nulla.")
        return 0

    done = 0
    with _engine().begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, payload, attempts, throttled_count FROM graph_outbox "
                "WHERE processed_at IS NULL AND attempts < :maxa "
                "  AND next_attempt_at <= now() "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim"
            ),
            {"maxa": _MAX_ATTEMPTS, "lim": limit},
        ).all()

        if not rows:
            return 0

        with driver.session() as neo:
            for row in rows:
                # Un savepoint per riga: senza, l'errore di UNA riga abortisce la
                # transazione della passata, e le righe sane gia' proiettate in
                # questo giro perdono il proprio `processed_at` — verrebbero
                # riapplicate al giro dopo per colpa di una vicina.
                savepoint = conn.begin_nested()
                try:
                    projector.apply(neo, row.payload)
                    conn.execute(
                        text("UPDATE graph_outbox SET processed_at = now() WHERE id = :id"),
                        {"id": row.id},
                    )
                    savepoint.commit()
                    done += 1
                except Exception as exc:  # noqa: BLE001 — registra e va avanti
                    savepoint.rollback()
                    _handle_failure(conn, row, exc)
    return done


def _handle_failure(conn, row, exc: Exception) -> None:
    """Mette da parte la riga o la rimanda indietro, senza far saltare la passata."""
    failure = retry.classify(
        exc,
        attempts=int(row.attempts),
        throttled=int(getattr(row, "throttled_count", 0) or 0),
        permanent=(InvalidGraphPayload,),
    )
    savepoint = conn.begin_nested()
    try:
        if failure.is_permanent:
            # Non e' un guasto: e' un payload che nessun tentativo puo' applicare.
            # Dirlo forte, una volta, invece di ripeterlo cinque volte piano.
            logger.error(
                "graph_outbox %s: payload non applicabile, spostata nel dead-letter (%s)",
                row.id, exc,
            )
            reason = str(exc)[:2000]
            conn.execute(_DEAD_LETTER, {"id": row.id, "reason": reason})
            conn.execute(_DROP_FROM_QUEUE, {"id": row.id})
        else:
            logger.warning(
                "graph_outbox %s fallita (%s), riprovo fra %.1fs",
                row.id, failure.kind, failure.delay_seconds, exc_info=True,
            )
            conn.execute(
                _RESCHEDULE,
                {
                    "spend": 1 if failure.consumes_attempt else 0,
                    "throttle": 1 if failure.kind == "throttled" else 0,
                    "e": str(exc)[:2000],
                    "delay": failure.delay_seconds,
                    "id": row.id,
                },
            )
        savepoint.commit()
    except Exception:  # noqa: BLE001 — nemmeno la contabilita' puo' fermare la coda
        savepoint.rollback()
        logger.exception("graph_outbox %s: esito non registrato", row.id)


def prune(older_than_days: int = 14) -> int:
    """Cancella le righe gia' proiettate piu' vecchie di N giorni (INV-2: la
    coda e' ricostruibile). Ritorna quante ne ha tolte."""
    with _engine().begin() as conn:
        return conn.execute(
            text(
                "DELETE FROM graph_outbox "
                "WHERE processed_at IS NOT NULL "
                "  AND processed_at < now() - make_interval(days => :d)"
            ),
            {"d": older_than_days},
        ).rowcount


def queue_stats() -> dict[str, int]:
    """`pending` = da processare, `stuck` = falliti troppe volte, `dead_letter`
    = messi da parte perche' non applicabili (payload che nessun tentativo
    digerisce). Le due ultime non sono la stessa cosa: la prima e' un guasto che
    puo' passare, la seconda e' un dato da guardare."""
    with _engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT "
                "  count(*) FILTER (WHERE processed_at IS NULL AND attempts < :m) AS pending, "
                "  count(*) FILTER (WHERE processed_at IS NULL AND attempts >= :m) AS stuck "
                "FROM graph_outbox"
            ),
            {"m": _MAX_ATTEMPTS},
        ).one()
        dead = conn.execute(
            text("SELECT count(*) FROM graph_outbox_dead_letter")
        ).scalar_one()
    return {"pending": int(row.pending), "stuck": int(row.stuck), "dead_letter": int(dead)}


def run_forever(idle_sleep: float = 2.0) -> None:
    logger.info("graph_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("graph_worker: passata fallita")
            processed = 0
        time.sleep(0.0 if processed else idle_sleep)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
