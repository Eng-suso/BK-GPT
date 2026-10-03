"""Worker: legge le fonti caricate e ne scrive testo ed evidenze ancorate.

Il caricamento conserva il file e mette la fonte in coda
(`acquisition_status == "pending"`); qui il file viene letto con il parser del
suo formato - docling-serve per PDF, DOCX e PPTX, openpyxl per Excel - e il
risultato finisce nell'Evidence Bucket (`workspace_source_evidence`,
`workspace_evidence_segments`).

Due fallimenti diversi, trattati in modo diverso:
- il file non e' leggibile (cifrato, rotto, XML non sicuro): riprovare dara'
  lo stesso esito, la fonte esce dalla coda come `failed` con il motivo;
- il lettore dei documenti non risponde: il file e' a posto, si riprova con
  backoff.

Ogni riga porta il proprio tenant, vincolato prima di leggere e rilasciato
dopo, anche quando la lettura fallisce.

Uso:
    from backend.workers.source_worker import drain_once
"""

from __future__ import annotations

import logging
import time

from backend import workspace_database as wd
from backend.security import reset_current_tenant_id, set_current_tenant_id

logger = logging.getLogger(__name__)

_IDLE_SLEEP_SECONDS = 3.0
# Un PDF lungo occupa docling-serve per minuti: due letture alla volta tengono
# la coda in movimento senza saturare il servizio.
_BATCH = 2


def _work_one(row: dict) -> bool:
    """Legge una fonte dentro il suo tenant.

    Returns:
        `True` se la fonte e' stata letta, `False` se no.
    """
    from backend.workspace_services.evidence.documents import DocumentServiceUnavailable
    from backend.workspace_services.source_ingestion import (
        SourceFileError,
        original_path,
        parse_source_file,
    )

    token = set_current_tenant_id(row["tenant_id"])
    try:
        try:
            payload = original_path(row["storage_key"] or "").read_bytes()
        except (SourceFileError, OSError) as exc:
            wd.fail_source_acquisition(row["id"], error="File originale non trovato.", permanent=True)
            logger.warning("fonte %s: originale non leggibile (%s)", row["id"], exc)
            return False
        try:
            parsed = parse_source_file(row["name"], payload, None)
        except SourceFileError as exc:
            wd.fail_source_acquisition(row["id"], error=str(exc), permanent=True)
            return False
        except DocumentServiceUnavailable as exc:
            wd.fail_source_acquisition(row["id"], error=str(exc), permanent=False)
            logger.warning("fonte %s: lettore dei documenti non disponibile, si riprova", row["id"])
            return False
        except Exception as exc:  # noqa: BLE001 - un guasto inatteso non ferma la coda
            logger.exception("fonte %s: lettura fallita", row["id"])
            wd.fail_source_acquisition(row["id"], error=f"Errore inatteso: {type(exc).__name__}", permanent=False)
            return False
        try:
            wd.complete_source_acquisition(row["id"], parsed)
        except Exception as exc:  # noqa: BLE001 - la scrittura fallita conta come tentativo
            # Senza questo la fonte restava `pending` e veniva ripresa a ogni
            # scadenza del lease, per sempre, senza che i tentativi salissero.
            logger.exception("fonte %s: scrittura delle evidenze fallita", row["id"])
            wd.fail_source_acquisition(
                row["id"], error=f"Scrittura fallita: {type(exc).__name__}", permanent=False
            )
            return False
        return True
    finally:
        reset_current_tenant_id(token)


def acquire_in_request(source_id: str, name: str, payload: bytes) -> dict | None:
    """Legge subito una fonte di testo semplice, con gli stessi esiti del worker.

    Il tenant e' gia' quello della richiesta. Se il worker la prende in carico
    nello stesso istante, la legge una seconda volta e scrive lo stesso esito.

    Returns:
        La fonte aggiornata, o `None` se nel frattempo e' sparita.
    """
    from backend.workspace_services.source_ingestion import SourceFileError, parse_source_file

    try:
        parsed = parse_source_file(name, payload, None)
    except SourceFileError as exc:
        return wd.fail_source_acquisition(source_id, error=str(exc), permanent=True)
    return wd.complete_source_acquisition(source_id, parsed)


def drain_once(limit: int = _BATCH, *, only_tenant_id: str | None = None) -> int:
    """Una passata sulla coda.

    Le fonti si prendono in carico una alla volta: una lettura puo' durare
    minuti, e un lotto preso tutto insieme farebbe scadere il lease del secondo
    file mentre il primo e' ancora in lettura.

    Returns:
        Quante fonti sono state lavorate, lette o no. Zero significa coda vuota.
    """
    processed = 0
    for _ in range(max(1, limit)):
        rows = wd.due_source_acquisitions(1, only_tenant_id=only_tenant_id)
        if not rows:
            break
        _work_one(rows[0])
        processed += 1
    # Prima si legge, poi si estrae: una fonte confermata in chat mentre era in
    # lettura entra in coda proprio alla fine della sua lettura.
    return processed + drain_claims_once(1, only_tenant_id=only_tenant_id)


def _extract_one(row: dict) -> bool:
    """Estrae le affermazioni di una fonte, dentro il suo tenant e la sua operazione.

    Returns:
        `True` se le affermazioni sono state scritte.
    """
    from backend.llm import OperationKind, operation
    from backend.workspace_services.evidence.claims import extract_claims

    token = set_current_tenant_id(row["tenant_id"])
    try:
        try:
            segments = wd.list_evidence_segments(row["id"])
            # L2: la spesa dell'estrazione appartiene a questa fonte, nel suo
            # progetto e processo.
            with operation(
                OperationKind.SOURCE_CLAIMS,
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                process_id=row["process_id"],
            ):
                result = extract_claims(segments, source_name=row["name"])
        except Exception as exc:  # noqa: BLE001 - un'estrazione storta non ferma la coda
            logger.exception("fonte %s: estrazione delle affermazioni fallita", row["id"])
            wd.fail_source_claims(row["id"], error=f"Estrazione non riuscita: {type(exc).__name__}", permanent=False)
            return False
        wd.complete_source_claims(row["id"], result, content_hash=row["content_hash"] or "")
        return True
    finally:
        reset_current_tenant_id(token)


def drain_claims_once(limit: int = 1, *, only_tenant_id: str | None = None) -> int:
    """Una passata sulla coda delle affermazioni (P1.12).

    Returns:
        Quante fonti sono state lavorate. Zero significa coda vuota.
    """
    processed = 0
    for _ in range(max(1, limit)):
        rows = wd.due_source_claims(1, only_tenant_id=only_tenant_id)
        if not rows:
            break
        _extract_one(rows[0])
        processed += 1
    return processed


def queue_stats() -> dict[str, int]:
    return wd.source_acquisition_stats()


def run_forever(idle_sleep: float = _IDLE_SLEEP_SECONDS) -> None:
    logger.info("source_worker avviato")
    while True:
        try:
            processed = drain_once()
        except Exception:  # noqa: BLE001 - una passata storta non ferma il loop
            logger.exception("source_worker: passata fallita")
            processed = 0
        if not processed:
            time.sleep(idle_sleep)


if __name__ == "__main__":  # pragma: no cover - entry point operativo
    logging.basicConfig(level=logging.INFO)
    run_forever()
