"""Worker: ricostruisce il piano dei processi la cui evidenza e' cambiata.

Il piano del processo - la `ProcessUnderstanding` dentro la review - nasceva
quando il consulente chiedeva di disegnare. Erano tre chiamate al modello dentro
il percorso critico di «Genera BPMN», cioe' il momento in cui qualcuno sta
guardando lo schermo e aspetta.

Il lavoro appartiene al momento in cui **la conoscenza cambia**: una fonte
salvata mette il processo in coda (`workspace_plan_materializations`), questo
worker la lavora, e quando arriva la richiesta di disegnare il piano e' gia' li'.

Diverso dagli altri worker del progetto: quelli drenano le code del canonical
e girano come `delir_worker`; qui il lavoro e' sul workspace operativo e usa
`ensure_process_plan`, che e' la stessa funzione del confine Process -> Canvas.
Nessuna seconda strada per costruire un piano: una sola, chiamata da due posti.

Ogni riga porta il proprio tenant, perche' il worker gira fuori da una richiesta
HTTP: il tenant viene vincolato prima di toccare il processo e rilasciato dopo,
sempre, anche quando la passata fallisce.

Uso:
    from backend.workers.plan_worker import drain_once, run_forever
    drain_once()          # una passata
    run_forever()         # loop (Ctrl-C per fermare)
"""

from __future__ import annotations

import logging
import time

from backend import workspace_database as wd
from backend.security import reset_current_tenant_id, set_current_tenant_id

logger = logging.getLogger(__name__)

_IDLE_SLEEP_SECONDS = 5.0
_BATCH = 5

# Esiti che chiudono la richiesta: il piano c'e' (costruito adesso o gia'
# aggiornato), oppure non c'e' niente da cui costruirlo. Nessuno dei tre
# migliora riprovando.
_SETTLED = frozenset({"synthesized", "reused", "no_evidence"})

# Esiti che non hanno senso ritentare: il processo non esiste piu'. Riprovarli
# cinque volte con backoff riempie i log e non cambia niente.
_PERMANENT = frozenset({"process_not_found"})


def _work_one(row: dict) -> bool:
    """Lavora una richiesta dentro il suo tenant.

    Returns:
        `True` se la riga e' stata chiusa, `False` se resta da riprovare.
    """
    from backend.agents.process_synthesis import ensure_process_plan

    token = set_current_tenant_id(row["tenant_id"])
    try:
        synthesis = ensure_process_plan(row["process_id"])
    except Exception as exc:  # noqa: BLE001 - una riga storta non ferma la coda
        logger.warning(
            "materializzazione piano fallita per il processo %s",
            row["process_id"],
            exc_info=True,
        )
        wd.fail_plan_materialization(row["id"], error=f"{type(exc).__name__}: {exc}")
        return False
    finally:
        reset_current_tenant_id(token)

    if synthesis.action in _SETTLED:
        wd.complete_plan_materialization(
            row["id"],
            action=synthesis.action,
            plan_version=synthesis.snapshot.version if synthesis.snapshot else None,
        )
        return True

    wd.fail_plan_materialization(
        row["id"],
        error=synthesis.reason or synthesis.action,
        # Un processo che non esiste non ricompare: la riga esce subito invece
        # di consumare quattro tentativi per dire la stessa cosa.
        max_attempts=1 if synthesis.action in _PERMANENT else wd.MATERIALIZATION_MAX_ATTEMPTS,
    )
    return False


def drain_once(limit: int = _BATCH) -> int:
    """Una passata sulla coda.

    Returns:
        Quante richieste sono state lavorate, riuscite o no. Zero significa coda
        vuota, ed e' cio' che il supervisore usa per decidere se dormire.
    """
    rows = wd.due_plan_materializations(limit)
    for row in rows:
        _work_one(row)
    return len(rows)


def queue_stats() -> dict[str, int]:
    return wd.plan_materialization_stats()


def prune() -> int:
    """Niente da potare: una riga lavorata resta, ed e' la memoria di cio' che
    il piano di quel processo ha attraversato."""
    return 0


def run_forever(idle_sleep: float = _IDLE_SLEEP_SECONDS) -> None:
    logger.info("plan_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001 - una passata storta non ferma il loop
            logger.exception("plan_worker: passata fallita")
            processed = 0
        if not processed:
            time.sleep(idle_sleep)


if __name__ == "__main__":  # pragma: no cover - entry point operativo
    logging.basicConfig(level=logging.INFO)
    run_forever()
