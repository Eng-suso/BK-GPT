"""Worker: drena `kg_ingest_queue` -> `canonical.write_evidence` (P5).

Diverso dagli altri due worker (`graph_worker`, `mem0_worker`): quelli drenano
un outbox di payload gia' materializzati e girano come `delir_worker` (nessun
accesso al dominio). Qui il payload e' l'**input grezzo** e il worker fa il
lavoro pesante — chunk + embedding + entity resolution (P2) + write atomico —
quindi gira come `delir_app` (`canonical_database_url`), con la sua DML di
dominio.

Ciclo di vita di una riga: `pending` -> (claim) `processing` -> `done` |
`failed` (dopo `_MAX_ATTEMPTS`). Un `processing` appeso da piu' di
`_STUCK_MINUTES` (worker morto) torna `pending`.

MVP mono-consultant: drena per `settings.default_consultant_id`. Il contesto
RLS solo-consultant, col pattern strict-client della 0013, vede tutte le righe
di quel consulente.
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy import text

from backend.db import canonical_session
from backend.memory.knowledge_graph import canonical
from backend.settings import settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
_STUCK_MINUTES = 30


def _consultant() -> str | None:
    return str(settings.default_consultant_id) if settings.default_consultant_id else None


def _requeue_stuck(consultant: str) -> None:
    with canonical_session(consultant) as session:
        session.execute(
            text(
                "UPDATE kg_ingest_queue SET status = 'pending' "
                "WHERE status = 'processing' "
                "  AND updated_at < now() - make_interval(mins => :m)"
            ),
            {"m": _STUCK_MINUTES},
        )


def _claim(consultant: str, limit: int) -> list:
    with canonical_session(consultant) as session:
        return session.execute(
            text(
                "UPDATE kg_ingest_queue "
                "SET status = 'processing', attempts = attempts + 1, updated_at = now() "
                "WHERE id IN ("
                "  SELECT id FROM kg_ingest_queue "
                "  WHERE status = 'pending' AND attempts < :maxa "
                "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim"
                ") RETURNING id, payload"
            ),
            {"maxa": _MAX_ATTEMPTS, "lim": limit},
        ).all()


def _finish(consultant: str, job_id: int, counts: dict) -> None:
    with canonical_session(consultant) as session:
        session.execute(
            text(
                "UPDATE kg_ingest_queue SET status = 'done', "
                "  result = CAST(:r AS jsonb), processed_at = now(), updated_at = now(), "
                "  last_error = NULL "
                "WHERE id = :i"
            ),
            {"r": json.dumps(counts), "i": job_id},
        )


def _fail(consultant: str, job_id: int, error: str) -> None:
    with canonical_session(consultant) as session:
        session.execute(
            text(
                "UPDATE kg_ingest_queue "
                "SET status = CASE WHEN attempts >= :maxa THEN 'failed' ELSE 'pending' END, "
                "    last_error = :e, updated_at = now() "
                "WHERE id = :i"
            ),
            {"maxa": _MAX_ATTEMPTS, "e": error[:2000], "i": job_id},
        )


def drain_once(limit: int = 20) -> int:
    """Processa fino a `limit` job. Ritorna quanti ne ha completati."""
    consultant = _consultant()
    if not consultant or not settings.canonical_database_url:
        return 0

    _requeue_stuck(consultant)
    claimed = _claim(consultant, limit)
    if not claimed:
        return 0

    done = 0
    for row in claimed:
        job_id = int(row.id)
        payload = {k: v for k, v in dict(row.payload).items() if k in canonical.EVIDENCE_KEYS}
        try:
            counts = canonical.write_evidence(**payload)
            _finish(consultant, job_id, counts)
            done += 1
        except Exception as exc:  # noqa: BLE001 — un job storto non ferma il worker
            logger.exception("kg_ingest_queue job %s fallito", job_id)
            _fail(consultant, job_id, str(exc))
    return done


def queue_stats() -> dict[str, int]:
    """`pending` = da processare, `stuck` = falliti troppe volte (dead-letter)."""
    consultant = _consultant()
    if not consultant or not settings.canonical_database_url:
        return {"pending": 0, "stuck": 0}
    with canonical_session(consultant) as session:
        row = session.execute(
            text(
                "SELECT "
                "  count(*) FILTER (WHERE status IN ('pending','processing') AND attempts < :m) AS pending, "
                "  count(*) FILTER (WHERE status = 'failed') AS stuck "
                "FROM kg_ingest_queue"
            ),
            {"m": _MAX_ATTEMPTS},
        ).one()
    return {"pending": int(row.pending), "stuck": int(row.stuck)}


def prune(older_than_days: int = 14) -> int:
    """Cancella i job `done` piu' vecchi di N giorni (l'input grezzo resta in
    `kg_source.content`)."""
    consultant = _consultant()
    if not consultant or not settings.canonical_database_url:
        return 0
    with canonical_session(consultant) as session:
        return session.execute(
            text(
                "DELETE FROM kg_ingest_queue WHERE status = 'done' "
                "  AND processed_at < now() - make_interval(days => :d)"
            ),
            {"d": older_than_days},
        ).rowcount


def run_forever(idle_sleep: float = 1.0) -> None:
    logger.info("ingest_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("ingest_worker: passata fallita")
            processed = 0
        time.sleep(0.0 if processed else idle_sleep)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
