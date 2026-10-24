"""Decisioni per elemento e confronto con le fonti (conformance): stato, rapporto
e la sua coda.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import and_, func, or_, select

from backend.workspace_database._common import now_iso, tenant_row
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    workspace_connection,
)


logger = logging.getLogger("backend.workspace_database")


ELEMENT_DECISIONS = frozenset({"confirmed", "rejected"})


class _ElementDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: Literal["confirmed", "rejected"]
    label: str = ""
    note: str = ""
    decided_at: str = ""
    plan_version: int = 0


def decode_element_decisions(review: WorkspaceBpmnReview) -> dict[str, dict]:
    """Le decisioni del consulente sugli elementi del piano, per riferimento.

    Ogni voce si valida da sola. Una voce rovinata si scarta e si scrive nei log;
    un intero documento illeggibile si scarta allo stesso modo. Non si solleva:
    una colonna rovinata renderebbe illeggibile l'intero processo, e il danno di
    perdere una conferma e' molto piu' piccolo - si riconferma, e il segno sul
    disegno torna "da confermare", che e' la parte prudente dell'errore.
    """
    raw = getattr(review, "element_decisions_json", None) or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "decisioni sugli elementi illeggibili per il modello %s: scartate",
            getattr(review, "bpmn_model_id", "?"),
        )
        return {}
    if not isinstance(parsed, dict):
        logger.warning(
            "decisioni sugli elementi non in forma di mappa per il modello %s: scartate",
            getattr(review, "bpmn_model_id", "?"),
        )
        return {}
    decisions: dict[str, dict] = {}
    for source_ref, value in parsed.items():
        try:
            decisions[str(source_ref)] = _ElementDecisionRecord.model_validate(value).model_dump()
        except ValidationError:
            logger.warning(
                "decisione non valida su %s per il modello %s: scartata",
                source_ref,
                getattr(review, "bpmn_model_id", "?"),
            )
    return decisions


def record_element_decision(
    bpmn_model_id: str,
    *,
    source_ref: str,
    label: str,
    decision: str,
    note: str = "",
) -> dict[str, dict]:
    """Registra che il consulente ha confermato o rifiutato un elemento del piano.

    Non passa da `assert_write_allowed`: e' una revisione umana fatta dal
    pannello delle evidenze, fuori da qualunque turno di chat, come l'approvazione
    di una review.

    Args:
        bpmn_model_id: Il modello a cui la review appartiene.
        source_ref: Il riferimento di tracciabilita' dell'elemento.
        label: L'etichetta dell'elemento al momento della decisione. Si tiene
            perche' un piano ricostruito puo' riusare lo stesso id per un
            passaggio diverso, e chi rilegge la decisione deve poterlo vedere.
        decision: `confirmed` o `rejected`.
        note: Perche', se il consulente lo scrive.

    Returns:
        Tutte le decisioni della review, dopo la scrittura.

    Raises:
        ValueError: Se la decisione non e' ammessa o la review non esiste.
    """
    if decision not in ELEMENT_DECISIONS:
        raise ValueError(f"Decisione non ammessa: {decision}")
    if not str(source_ref or "").strip():
        raise ValueError("Riferimento dell'elemento obbligatorio.")

    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            raise ValueError(f"Review BPMN non trovata: {bpmn_model_id}")
        decisions = decode_element_decisions(review)
        decisions[source_ref] = {
            "decision": decision,
            "label": label,
            "note": note.strip(),
            "decided_at": now_iso(),
            "plan_version": int(getattr(review, "version", 1) or 1),
        }
        review.element_decisions_json = json.dumps(decisions, ensure_ascii=False)
        review.updated_at = now_iso()
        session.flush()
        return decisions


def conformance_state(review: WorkspaceBpmnReview) -> dict:
    """Lo stato del confronto disegno-piano-fonti di questa review.

    `status` dice se un confronto e' in attesa di girare; `report` e' l'ultimo
    esito, che resta leggibile anche mentre il prossimo e' in coda: il consulente
    continua a vedere cosa risultava, con l'avviso che le cose sono cambiate.
    """
    return {
        "status": getattr(review, "conformance_status", None) or "none",
        "report": decode_conformance_report(review),
    }


def decode_conformance_report(review: WorkspaceBpmnReview) -> dict | None:
    """L'ultima verifica di conformita' registrata, se leggibile.

    Un rapporto illeggibile vale come nessun rapporto: chi lo legge deve rifare
    la verifica, non fidarsi di un dato rovinato.
    """
    raw = getattr(review, "conformance_json", None)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "rapporto di conformita' illeggibile per il modello %s: ignorato",
            getattr(review, "bpmn_model_id", "?"),
        )
        return None
    return parsed if isinstance(parsed, dict) else None


def record_conformance_report(
    bpmn_model_id: str, report: dict, *, only_if_running: bool = False
) -> dict | None:
    """Registra sulla review l'esito dell'ultima verifica disegno-piano-fonti.

    Non alza la versione del piano e non passa da `assert_write_allowed`: e' la
    registrazione di un controllo, come la coda di materializzazione, non una
    modifica del processo. Il rapporto porta lo snapshot e l'impronta del canvas
    su cui e' stato fatto, quindi chi lo rilegge sa se vale ancora.

    Args:
        bpmn_model_id: Il disegno a cui appartiene la review.
        report: Il rapporto da registrare.
        only_if_running: Chiude il confronto solo se la presa in carico c'e'
            ancora. E' il worker: mentre leggeva le fonti un disegno nuovo puo'
            aver rimesso la riga in coda, e segnarla `done` perderebbe quel
            confronto. Il rapporto si registra comunque.

    Returns:
        Il rapporto registrato, o ``None`` se la review non esiste nel tenant.
    """
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            return None
        session.refresh(review, with_for_update=True)
        review.conformance_json = json.dumps(report, ensure_ascii=False)
        if not only_if_running or review.conformance_status == "running":
            review.conformance_status = "done"
            review.conformance_leased_at = None
        session.flush()
        return report


def request_conformance_check(bpmn_model_id: str) -> bool:
    """Segna che il confronto con le fonti va rifatto.

    Lo scrivono le operazioni che cambiano cio' che il confronto guarda: una
    bozza appena disegnata, un canvas salvato, un piano rivisto. Il disegno esce
    subito e la verifica gira dietro - il consulente itera invece di aspettare -
    e finche' non e' finita il pannello dice che e' in corso.

    Non alza la versione del piano e non passa da `assert_write_allowed`: e' la
    registrazione di un lavoro da fare, come la coda di materializzazione.

    Returns:
        `True` se la richiesta e' stata registrata; `False` se il processo non ha
        una review (niente piano, niente da confrontare).
    """
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            return False
        _queue_conformance(review)
        session.flush()
        return True


def _queue_conformance(review: WorkspaceBpmnReview) -> None:
    """Rimette in coda il confronto di un disegno nuovo, con i tentativi a zero.

    I tentativi contano i fallimenti dello stesso disegno: quando il disegno o
    il piano cambiano, il confronto e' un altro e riparte da capo.
    """
    review.conformance_status = "pending"
    review.conformance_attempts = 0


def due_conformance_checks(limit: int = 3, *, only_tenant_id: str | None = None) -> list[dict]:
    """I confronti in attesa, i piu' vecchi per primi, presi in carico con una scadenza.

    Come la coda dei piani: il worker gira fuori da una richiesta HTTP, quindi la
    riga porta il proprio tenant, e chi la prende in carico lo vincola prima di
    leggere il processo. La presa in carico marca `running` **e quando**: una
    lettura delle fonti dura minuti, e se il processo che la stava facendo muore -
    un riavvio, un deploy - la riga deve tornare eleggibile da sola. Senza la
    scadenza resta `running` per sempre, nessuno la rilavora, e il pannello mostra
    "Confronto in corso" all'infinito: sembra lavoro in corso e non lo e'.

    Args:
        limit: Quante righe prendere in carico.
        only_tenant_id: Limita la coda a un tenant. I test drenano cosi', perche'
            una passata che prende la riga di un altro workspace scriverebbe un
            rapporto dentro il processo di un cliente.

    Side effects:
        Marca le righe prese in carico e ne segna l'istante.
    """
    expired_before = (
        datetime.now(UTC) - timedelta(seconds=CONFORMANCE_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceBpmnReview)
            .where(
                or_(
                    WorkspaceBpmnReview.conformance_status == "pending",
                    and_(
                        WorkspaceBpmnReview.conformance_status == "running",
                        or_(
                            WorkspaceBpmnReview.conformance_leased_at.is_(None),
                            WorkspaceBpmnReview.conformance_leased_at < expired_before,
                        ),
                    ),
                )
            )
            .order_by(WorkspaceBpmnReview.updated_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        claimed = []
        now = now_iso()
        for row in rows:
            if (row.conformance_attempts or 0) >= CONFORMANCE_MAX_ATTEMPTS:
                # Ha gia' avuto i suoi tentativi e nessuno e' arrivato in fondo:
                # esce dalla coda invece di girare per sempre, e resta contata.
                logger.warning(
                    "confronto con le fonti abbandonato per il processo %s dopo %s tentativi",
                    row.process_id,
                    row.conformance_attempts,
                )
                row.conformance_status = CONFORMANCE_FAILED
                row.conformance_leased_at = None
                continue
            row.conformance_status = "running"
            row.conformance_leased_at = now
            row.conformance_attempts = (row.conformance_attempts or 0) + 1
            claimed.append(
                {
                    "tenant_id": row.tenant_id,
                    "process_id": row.process_id,
                    "bpmn_model_id": row.bpmn_model_id,
                }
            )
        session.flush()
        return claimed


def enqueue_unchecked_conformance(limit: int = 20, *, only_tenant_id: str | None = None) -> list[str]:
    """Mette in coda i processi che hanno un disegno e non sono mai stati confrontati.

    La coda si riempie quando qualcuno disegna o rivede un piano. Da sola quella
    regola coprirebbe solo i processi toccati da quando il confronto esiste: tutti
    i disegni gia' sul tavolo - gli altri progetti, gli altri clienti - resterebbero
    senza verifica per sempre, e il pannello direbbe "non ancora confrontato"
    finche' qualcuno non li riapre. Qui entrano anche loro, un po' per passata.

    Args:
        limit: Quanti processi mettere in coda al massimo.
        only_tenant_id: Limita a un tenant (amministrazione, test).

    Returns:
        Gli id dei modelli messi in coda.
    """
    with workspace_connection() as session:
        statement = (
            select(WorkspaceBpmnReview)
            .join(WorkspaceBpmnModel, WorkspaceBpmnModel.id == WorkspaceBpmnReview.bpmn_model_id)
            .where(WorkspaceBpmnReview.conformance_status.is_(None))
            .where(WorkspaceBpmnModel.xml.is_not(None))
            .order_by(WorkspaceBpmnReview.updated_at)
            .limit(max(1, int(limit)))
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        for row in rows:
            _queue_conformance(row)
        session.flush()
        return [row.bpmn_model_id for row in rows]


# Per quanto una riga presa in carico resta invisibile agli altri worker. Piu'
# larga di quella dei piani perche' un confronto legge una fonte per volta con il
# modello: sui processi veri sono minuti, e una scadenza stretta farebbe lavorare
# due volte lo stesso disegno.
CONFORMANCE_LEASE_SECONDS = 900


# Prese in carico per lo stesso disegno prima di smettere. Con il lease da 15
# minuti sono piu' di un'ora di tentativi: abbastanza per un provider che torna,
# non abbastanza per riempire il log di un errore che non passera'.
CONFORMANCE_MAX_ATTEMPTS = 5


CONFORMANCE_FAILED = "failed"


# Lo stato di chi ha rinunciato: la review salvata non e' leggibile, e la coda
# non la ripropone. Non e' `done` - nessun confronto e' stato fatto - e non e'
# `pending`, altrimenti la stessa riga girerebbe per sempre. Torna in coda solo
# quando qualcuno tocca il piano (`request_conformance_check`).
CONFORMANCE_UNAVAILABLE = "unavailable"


def conformance_queue_stats(*, only_tenant_id: str | None = None) -> dict[str, int]:
    """Quanti confronti sono in attesa, presi in carico, o rinunciati.

    Args:
        only_tenant_id: Limita il conto a un tenant (amministrazione, test).
    """
    statement = select(WorkspaceBpmnReview.conformance_status, func.count()).group_by(
        WorkspaceBpmnReview.conformance_status
    )
    if only_tenant_id:
        statement = statement.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
    with workspace_connection() as session:
        rows = session.execute(statement).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0),
        "stuck": counts.get("running", 0),
        # Disegni che la coda ha smesso di riprovare: il piano salvato non si
        # legge. Contarli separatamente e' l'unico modo per accorgersene, invece
        # di vederli sparire dentro "done" come se fossero stati confrontati.
        "unavailable": counts.get(CONFORMANCE_UNAVAILABLE, 0),
        # Disegni che hanno esaurito i tentativi: errori ripetuti, non un
        # piano illeggibile. Anche questi vanno guardati da una persona.
        "failed": counts.get(CONFORMANCE_FAILED, 0),
    }


def release_conformance_check(
    bpmn_model_id: str, *, status: str = "pending", only_if_running: bool = False
) -> None:
    """Rimette una presa in carico nello stato dato (riprova, o resa).

    Con `only_if_running` (il worker) non tocca una riga che un disegno nuovo ha
    rimesso in coda nel frattempo: quel confronto e' un altro e va fatto.
    """
    with workspace_connection() as session:
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is None:
            return
        session.refresh(review, with_for_update=True)
        if only_if_running and review.conformance_status != "running":
            return
        review.conformance_status = status
        review.conformance_leased_at = None
        session.flush()
