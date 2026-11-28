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

Un consulente per account: il worker chiede prima, come `delir_worker`, quali
consulenti hanno job in coda (solo id e stato, mai il payload: 0020), poi drena
ognuno nel suo contesto RLS solo-consultant, che col pattern strict-client della
0013 vede tutte le righe di quel consulente, e nel suo spazio di lavoro.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text

from backend.llm import spend_cap
from backend.db import canonical_session
from backend.llm import OperationKind, operation
from backend.memory.knowledge_graph import canonical
from backend.security import (
    reset_current_tenant_id,
    set_current_tenant_id,
    tenant_id_for_consultant,
)
from backend.services import degradation_counters
from backend.settings import settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
_STUCK_MINUTES = 30


@lru_cache(maxsize=1)
def _owners_engine():
    return create_engine(settings.canonical_worker_url, future=True, pool_pre_ping=True)


def _consultants(statuses: tuple[str, ...]) -> list[str]:
    """I consulenti con almeno un job in uno di questi stati.

    Senza la DSN di `delir_worker` (sviluppo minimo) resta il solo consulente
    di default, come prima degli account.
    """
    if not settings.canonical_database_url:
        return []
    if not settings.canonical_worker_url:
        default = settings.default_consultant_id
        return [str(default)] if default else []
    with _owners_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT consultant_id FROM kg_ingest_queue "
                "WHERE status = ANY(:s) ORDER BY consultant_id"
            ),
            {"s": list(statuses)},
        ).all()
    return [str(row.consultant_id) for row in rows]


@contextmanager
def _working_for(consultant: str):
    """Il lavoro di un consulente gira nel suo spazio: consumi e letture sono suoi."""
    tenant_id = tenant_id_for_consultant(consultant)
    token = set_current_tenant_id(tenant_id) if tenant_id else None
    try:
        yield
    finally:
        if token is not None:
            reset_current_tenant_id(token)


def _requeue_stuck(consultant: str) -> None:
    with canonical_session(consultant) as session:
        requeued = session.execute(
            text(
                "UPDATE kg_ingest_queue SET status = 'pending' "
                "WHERE status = 'processing' "
                "  AND updated_at < now() - make_interval(mins => :m) "
                "RETURNING id"
            ),
            {"m": _STUCK_MINUTES},
        ).all()
    if requeued:
        # ATTENZIONE: un job 'processing' appeso PUO' aver gia' committato
        # write_evidence (crash tra commit e mark 'done'). Riprocessarlo puo'
        # duplicare claim/gap/impact (INSERT non idempotenti). Reso visibile;
        # il fix strutturale e' una chiave di idempotenza a livello DB.
        degradation_counters.bump(
            "kg_ingest_worker", "requeued_stuck",
            detail=f"job ids {[r.id for r in requeued]}",
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


def _fail(consultant: str, job_id: int, error: str, *, consume_attempt: bool = True) -> None:
    if not consume_attempt:
        with canonical_session(consultant) as session:
            session.execute(
                text(
                    "UPDATE kg_ingest_queue "
                    "SET status = 'pending', attempts = GREATEST(attempts - 1, 0), "
                    "    last_error = :e, updated_at = now() "
                    "WHERE id = :i"
                ),
                {"e": error[:2000], "i": job_id},
            )
        return
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
    """Processa fino a `limit` job, consulente per consulente. Ritorna quanti ne ha completati.

    Il limite si divide fra chi ha lavoro in coda: un account con cento
    documenti da leggere non fa aspettare quello che ne ha caricato uno.
    """
    consultants = _consultants(("pending", "processing"))
    if not consultants:
        return 0
    share = max(1, limit // len(consultants))
    done = 0
    for consultant in consultants:
        if done >= limit:
            break
        with _working_for(consultant):
            done += _drain_consultant(consultant, min(share, limit - done))
    return done


def _drain_consultant(consultant: str, limit: int) -> int:
    _requeue_stuck(consultant)
    claimed = _claim(consultant, limit)
    if not claimed:
        return 0

    done = 0
    for row in claimed:
        job_id = int(row.id)
        # Il freno puo' scattare a meta' del lotto gia' preso: i job che restano
        # tornano in coda senza partire e senza consumare il tentativo, invece di
        # restare `processing` o di finire in dead-letter.
        if spend_cap.tripped():
            _fail(consultant, job_id, spend_cap.MESSAGE, consume_attempt=False)
            continue
        raw = dict(row.payload)
        payload = {k: v for k, v in raw.items() if k in canonical.EVIDENCE_KEYS}
        try:
            # Punto d'ingresso dell'ingestione: qui dentro girano gli embedding e
            # il giudizio di entity resolution sui casi che il confronto
            # deterministico non ha chiuso. Senza operazione aperta il gateway
            # rifiuta, l'`except` largo del resolver lo inghiotte e il grafo
            # accumula duplicati in silenzio - il guasto peggiore, perche' non si
            # vede.
            #
            # L'operazione porta gli id **workspace**, non quelli canonical del
            # pacchetto: il registro dei consumi ha una colonna `project_id` sola,
            # e la chat spende sugli id workspace. Mettercene due spazi diversi
            # renderebbe «quanto costa questo progetto» un raggruppamento che
            # divide in due lo stesso progetto. I job accodati prima di questo
            # campo non li hanno: per quelli si ricade sugli id canonical, che e'
            # meglio di niente e si riconosce a occhio (uuid canonical).
            with operation(
                OperationKind.KG_INGESTION,
                project_id=raw.get("workspace_project_id") or payload.get("project_id"),
                process_id=raw.get("workspace_process_id") or payload.get("process_id"),
                user_id=raw.get("user_id"),
            ):
                counts = canonical.write_evidence(**payload)
        except spend_cap.SpendCapReached as exc:
            # Il freno d'emergenza non e' un difetto del job: torna in coda senza
            # consumare il tentativo.
            _fail(consultant, job_id, str(exc), consume_attempt=False)
            continue
        except Exception as exc:  # noqa: BLE001 — un job storto non ferma il worker
            logger.exception("kg_ingest_queue job %s fallito", job_id)
            _fail(consultant, job_id, str(exc))
            continue

        # write_evidence ha COMMITTATO. write_evidence NON e' idempotente a
        # livello di pacchetto (claim/gap/impact sono INSERT puri): NON far
        # ripassare questo job. Se il mark 'done' non riesce, ritenta qualche
        # volta e poi lascia la riga 'processing' (verra' segnalata come stuck,
        # non riprocessata alla cieca).
        if not _mark_done(consultant, job_id, counts):
            degradation_counters.bump(
                "kg_ingest_worker", "finish_failed",
                detail=f"job {job_id} scritto ma non marcato done",
            )
        done += 1
    return done


def _mark_done(consultant: str, job_id: int, counts: dict, *, tries: int = 3) -> bool:
    for attempt in range(tries):
        try:
            _finish(consultant, job_id, counts)
            return True
        except Exception:  # noqa: BLE001
            logger.warning(
                "kg_ingest_queue job %s: _finish tentativo %d/%d fallito",
                job_id, attempt + 1, tries, exc_info=True,
            )
    return False


def queue_stats() -> dict[str, int]:
    """`pending` = da processare, `stuck` = falliti troppe volte (dead-letter)."""
    sql = text(
        "SELECT "
        "  count(*) FILTER (WHERE status IN ('pending','processing') AND attempts < :m) AS pending, "
        "  count(*) FILTER (WHERE status = 'failed') AS stuck "
        "FROM kg_ingest_queue"
    )
    if not settings.canonical_database_url:
        return {"pending": 0, "stuck": 0}
    if settings.canonical_worker_url:
        # Il worker vede stato e tentativi di tutti i job (0020): un conteggio solo.
        with _owners_engine().connect() as conn:
            row = conn.execute(sql, {"m": _MAX_ATTEMPTS}).one()
        return {"pending": int(row.pending), "stuck": int(row.stuck)}
    totals = {"pending": 0, "stuck": 0}
    for consultant in _consultants(("pending", "processing", "failed")):
        with canonical_session(consultant) as session:
            row = session.execute(sql, {"m": _MAX_ATTEMPTS}).one()
        totals["pending"] += int(row.pending)
        totals["stuck"] += int(row.stuck)
    return totals


def prune(older_than_days: int = 14) -> int:
    """Cancella i job `done` piu' vecchi di N giorni (l'input grezzo resta in
    `kg_source.content`)."""
    removed = 0
    for consultant in _consultants(("done",)):
        with canonical_session(consultant) as session:
            removed += session.execute(
                text(
                    "DELETE FROM kg_ingest_queue WHERE status = 'done' "
                    "  AND processed_at < now() - make_interval(days => :d)"
                ),
                {"d": older_than_days},
            ).rowcount
    return removed


def run_forever(idle_sleep: float = 1.0) -> None:
    logger.info("ingest_worker avviato")
    while True:
        spend_cap.pause_while_tripped("ingest_worker")
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("ingest_worker: passata fallita")
            processed = 0
        time.sleep(0.0 if processed else idle_sleep)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
