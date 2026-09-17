"""Worker: confronta con le fonti i disegni che sono cambiati.

Il confronto costa una chiamata al modello per fonte, e su un processo vero sono
minuti. Dentro «Genera BPMN» quei minuti li aspettava il consulente davanti allo
schermo, prima di vedere qualunque cosa - ed e' il momento in cui serve invece
poter guardare il disegno, correggerlo, riprovare.

Qui il lavoro sta dopo: chi disegna o salva il canvas segna la review
(`request_conformance_check`), questo worker lavora la coda e scrive l'esito, e
il pannello Evidenze lo mostra quando arriva. Il disegno esce in pochi secondi,
la verifica arriva quando e' pronta, e nel frattempo il pannello dice che e' in
corso invece di dichiarare conforme cio' che nessuno ha ancora guardato.

La riparazione del piano non e' di questo worker: cambiare il disegno mentre il
consulente lo sta leggendo e' una sorpresa, non un miglioramento. I punti aperti
restano nel pannello, con il bottone che li integra quando lo decide lui.

Uso:
    from backend.workers.conformance_worker import drain_once, run_forever
"""

from __future__ import annotations

import logging
import time

from backend import workspace_database as wd
from backend.security import reset_current_tenant_id, set_current_tenant_id

logger = logging.getLogger(__name__)

_IDLE_SLEEP_SECONDS = 5.0
# Quanti confronti per passata. Ognuno e' una chiamata per fonte: due processi
# insieme bastano a tenere la coda vuota senza aprire venti connessioni al
# provider.
_BATCH = 2


def _work_one(row: dict) -> bool:
    """Confronta un processo dentro il suo tenant.

    Returns:
        `True` se il confronto e' stato scritto, `False` se va riprovato.
    """
    from backend.agents.conformance_audit import audit_process_conformance

    token = set_current_tenant_id(row["tenant_id"])
    try:
        report = audit_process_conformance(row["process_id"])
    except Exception:  # noqa: BLE001 - un processo storto non ferma la coda
        logger.warning(
            "confronto con le fonti fallito per il processo %s", row["process_id"], exc_info=True
        )
        wd.release_conformance_check(row["bpmn_model_id"], status="pending")
        return False
    finally:
        reset_current_tenant_id(token)

    if report is None:
        # Il processo non esiste piu': la presa in carico non torna in coda,
        # altrimenti la stessa riga girerebbe per sempre.
        token = set_current_tenant_id(row["tenant_id"])
        try:
            wd.release_conformance_check(row["bpmn_model_id"], status="done")
        finally:
            reset_current_tenant_id(token)
        return False
    return True


def drain_once(limit: int = _BATCH) -> int:
    """Una passata sulla coda dei confronti."""
    rows = wd.due_conformance_checks(limit)
    for row in rows:
        _work_one(row)
    return len(rows)


def queue_stats() -> dict[str, int]:
    return wd.conformance_queue_stats()


def prune() -> int:
    """Niente da potare: l'esito resta sulla review, ed e' cio' che il pannello legge."""
    return 0


def run_forever(idle_sleep: float = _IDLE_SLEEP_SECONDS) -> None:
    logger.info("conformance_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001 - una passata storta non ferma il loop
            logger.exception("conformance_worker: passata fallita")
            processed = 0
        if not processed:
            time.sleep(idle_sleep)


if __name__ == "__main__":  # pragma: no cover - entry point operativo
    logging.basicConfig(level=logging.INFO)
    run_forever()
