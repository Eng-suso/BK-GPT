"""Worker che drena graph_outbox e proietta su Neo4j (INV-7).

Gira come ruolo delir_worker (`canonical_worker_url`): SELECT/UPDATE solo sulle
due code, nessun accesso alle tabelle di dominio. Il payload e' gia' completo,
il worker non rilegge Postgres.

MVP: worker singolo, ordine globale per `id`. L'ordinamento per-aggregate e il
retry/backoff avanzato sono un refinement di P5/P8.

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
from backend.settings import settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5


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
                "SELECT id, payload FROM graph_outbox "
                "WHERE processed_at IS NULL AND attempts < :maxa "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim"
            ),
            {"maxa": _MAX_ATTEMPTS, "lim": limit},
        ).all()

        if not rows:
            return 0

        with driver.session() as neo:
            for row in rows:
                try:
                    projector.apply(neo, row.payload)
                    conn.execute(
                        text("UPDATE graph_outbox SET processed_at = now() WHERE id = :id"),
                        {"id": row.id},
                    )
                    done += 1
                except Exception as exc:  # noqa: BLE001 — registra e va avanti
                    logger.exception("graph_outbox %s fallita", row.id)
                    conn.execute(
                        text(
                            "UPDATE graph_outbox "
                            "SET attempts = attempts + 1, last_error = :e WHERE id = :id"
                        ),
                        {"e": str(exc)[:2000], "id": row.id},
                    )
    return done


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
