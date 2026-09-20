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
# Ogni quanto, a coda vuota, si cercano i disegni che nessuno ha mai confrontato.
# Sono i processi di prima che il confronto esistesse: i progetti degli altri
# clienti, non solo quello su cui si sta lavorando adesso.
_SWEEP_INTERVAL_SECONDS = 600.0
_last_sweep_at: float | None = None
# Quanti confronti per passata. Ognuno e' una chiamata per fonte: due processi
# insieme bastano a tenere la coda vuota senza aprire venti connessioni al
# provider.
_BATCH = 2


def _work_one(row: dict) -> bool:
    """Confronta un processo dentro il suo tenant.

    Un fallimento non e' sempre lo stesso fallimento. Se il piano salvato non si
    legge - semantic model legacy, ProcessUnderstanding placeholder - riprovare
    dara' lo stesso errore per sempre: la riga esce dalla coda e lo dice. Se
    invece e' andata storta la lettura delle fonti, la presa in carico **non** si
    rilascia: la riga resta invisibile finche' il lease non scade, e quello e' il
    tempo di attesa prima del prossimo tentativo. Rilasciarla subito a `pending`
    la rimetteva in cima alla passata successiva, che e' come il 2026-09-20 la
    coda ha riempito il log con lo stesso traceback centinaia di volte.

    Returns:
        `True` se il confronto e' stato scritto, `False` se no.
    """
    from backend.agents.conformance_audit import audit_process_conformance
    from backend.llm import OperationKind, operation

    token = set_current_tenant_id(row["tenant_id"])
    try:
        # Il punto d'ingresso del confronto: la spesa del revisore appartiene a
        # questa riga di coda, non al processo in generale.
        with operation(
            OperationKind.CONFORMANCE_AUDIT,
            tenant_id=row["tenant_id"],
            process_id=row["process_id"],
        ):
            report = audit_process_conformance(row["process_id"])
    except wd.UnreadableReviewError:
        logger.warning(
            "confronto impossibile per il processo %s: il piano salvato non e' leggibile, "
            "va rigenerato. Fuori dalla coda finche' qualcuno non lo tocca.",
            row["process_id"],
            exc_info=True,
        )
        wd.release_conformance_check(row["bpmn_model_id"], status=wd.CONFORMANCE_UNAVAILABLE)
        return False
    except Exception:  # noqa: BLE001 - un processo storto non ferma la coda
        logger.warning(
            "confronto con le fonti fallito per il processo %s: riprovo alla scadenza della "
            "presa in carico",
            row["process_id"],
            exc_info=True,
        )
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


def sweep_unchecked(*, force: bool = False) -> int:
    """Mette in coda i disegni mai confrontati, al piu' ogni tanto.

    Returns:
        Quanti processi ha messo in coda.
    """
    global _last_sweep_at
    now = time.monotonic()
    if not force and _last_sweep_at is not None and now - _last_sweep_at < _SWEEP_INTERVAL_SECONDS:
        return 0
    _last_sweep_at = now
    try:
        queued = wd.enqueue_unchecked_conformance()
    except Exception:  # noqa: BLE001 - uno sweep storto non ferma la coda
        logger.warning("sweep dei disegni mai confrontati non riuscito", exc_info=True)
        return 0
    if queued:
        logger.info("sweep: %s disegni mai confrontati messi in coda", len(queued))
    return len(queued)


def drain_once(limit: int = _BATCH, *, only_tenant_id: str | None = None) -> int:
    """Una passata sulla coda dei confronti.

    Args:
        limit: Quanti confronti lavorare.
        only_tenant_id: Limita la passata a un tenant. Serve a chi drena a mano -
            i test, l'amministrazione - per non lavorare la coda di un altro
            workspace.
    """
    rows = wd.due_conformance_checks(limit, only_tenant_id=only_tenant_id)
    for row in rows:
        _work_one(row)
    return len(rows)


def drain_and_sweep(limit: int = _BATCH) -> int:
    """La passata del loop di servizio: la coda, e a coda vuota i mai confrontati.

    Separata da `drain_once` per lo stesso motivo del piano: chi drena a mano
    vuole lavorare la coda che vede, non quella che uno sweep su tutti i tenant
    potrebbe riempire nel frattempo.
    """
    processed = drain_once(limit)
    if processed:
        return processed
    if sweep_unchecked():
        return drain_once(limit)
    return 0


def queue_stats() -> dict[str, int]:
    return wd.conformance_queue_stats()


def prune() -> int:
    """Niente da potare: l'esito resta sulla review, ed e' cio' che il pannello legge."""
    return 0


def run_forever(idle_sleep: float = _IDLE_SLEEP_SECONDS) -> None:
    logger.info("conformance_worker avviato")
    while True:
        try:
            processed = drain_and_sweep()
        except Exception:  # noqa: BLE001 - una passata storta non ferma il loop
            logger.exception("conformance_worker: passata fallita")
            processed = 0
        if not processed:
            time.sleep(idle_sleep)


if __name__ == "__main__":  # pragma: no cover - entry point operativo
    logging.basicConfig(level=logging.INFO)
    run_forever()
