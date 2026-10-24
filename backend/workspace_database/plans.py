"""Estrazioni del piano, audit delle fonti e la coda che ricostruisce il piano di
un processo.
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from backend.workspace_database._common import now_iso, tenant_id
from backend.workspace_storage import (
    WorkspaceBpmnReview,
    WorkspacePlanExtraction,
    WorkspacePlanMaterialization,
    WorkspaceProcess,
    WorkspaceSource,
    WorkspaceSourceAudit,
    workspace_connection,
)


MATERIALIZATION_MAX_ATTEMPTS = 5


MATERIALIZATION_BACKOFF_SECONDS = 30


# Per quanto una riga presa in carico resta invisibile agli altri worker. Non e'
# uno stato `running` - un lease che nessuno rilascia e' il modo in cui una coda
# si blocca in silenzio - ma una scadenza: se chi l'ha presa muore, la riga torna
# eleggibile da sola.
MATERIALIZATION_LEASE_SECONDS = 300


def _materialization_to_dict(row: WorkspacePlanMaterialization) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "process_id": row.process_id,
        "status": row.status,
        "requested_at": row.requested_at,
        "reason": row.reason,
        "attempts": row.attempts,
        "next_attempt_at": row.next_attempt_at,
        "last_error": row.last_error,
        "completed_at": row.completed_at,
        "last_action": row.last_action,
        "plan_version": row.plan_version,
    }


def _plan_extraction_to_dict(row: WorkspacePlanExtraction) -> dict:
    return {
        "id": row.id,
        "artifact_key": row.artifact_key,
        "source_id": row.source_id,
        "source_name": row.source_name,
        "input_digest": row.input_digest,
        "prompt_version": row.prompt_version,
        "model": row.model,
        "plan": json.loads(row.plan_json or "{}"),
        "created_at": row.created_at,
    }


def plan_extractions_by_key(keys: list[str]) -> dict[str, dict]:
    """I piani parziali gia' estratti, fra quelli chiesti.

    Una query per tutta la sintesi, non una per fonte: con cinque interviste
    sarebbero cinque viaggi al database per rispondere a una domanda sola, e il
    punto di questo artefatto e' rendere una ricostruzione piu' economica.

    Args:
        keys: Le chiavi degli artefatti, non affidabili.

    Returns:
        Gli artefatti trovati, per chiave. Le chiavi assenti semplicemente non
        compaiono: non si sa distinguere "mai estratto" da "estratto e poi
        cancellato", e non serve saperlo.

    Sola lettura, dentro il tenant corrente.
    """
    wanted = [key for key in dict.fromkeys(keys) if key]
    if not wanted:
        return {}
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspacePlanExtraction)
                .where(WorkspacePlanExtraction.tenant_id == tenant_id())
                .where(WorkspacePlanExtraction.artifact_key.in_(wanted))
            )
            .scalars()
            .all()
        )
        return {row.artifact_key: _plan_extraction_to_dict(row) for row in rows}


def save_plan_extraction(
    *,
    artifact_key: str,
    plan: dict,
    source_id: str = "",
    source_name: str = "",
    input_digest: str = "",
    prompt_version: str = "",
    model: str = "",
) -> dict:
    """Registra il piano parziale ricavato da una fonte, una volta sola.

    Non e' una scrittura sul processo e non passa da `assert_write_allowed`:
    l'artefatto e' la registrazione di un lavoro gia' pagato, e una modalita' di
    chat che permette di estrarre ma non di prenderne nota farebbe ripagare la
    stessa estrazione al giro dopo.

    Riscrivere un artefatto gia' presente non ha senso - la chiave contiene
    tutto cio' che determina il risultato - quindi qui si tiene il primo. E'
    anche cio' che rende innocua la gara fra due sintesi dello stesso processo.

    Args:
        artifact_key: L'identita' dell'estrazione, non affidabile.
        plan: Il piano parziale, gia' serializzato in JSON.
        source_id: La fonte da cui veniva, per leggere la tabella.
        source_name: Il nome della fonte, idem.
        input_digest: L'impronta del testo letto.
        prompt_version: La versione del prompt che l'ha prodotto.
        model: Il modello che l'ha prodotto.

    Returns:
        L'artefatto salvato, o quello che c'era gia'.

    Raises:
        ValueError: Se la chiave e' vuota. Un artefatto senza identita' non si
            ritrova, e scriverlo riempirebbe la tabella di righe irraggiungibili.
    """
    key = str(artifact_key or "").strip()
    if not key:
        raise ValueError("Un artefatto di estrazione senza chiave non si ritrova.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing = (
            session.execute(
                select(WorkspacePlanExtraction)
                .where(WorkspacePlanExtraction.tenant_id == current_tenant_id)
                .where(WorkspacePlanExtraction.artifact_key == key)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return _plan_extraction_to_dict(existing)

        row = WorkspacePlanExtraction(
            tenant_id=current_tenant_id,
            artifact_key=key,
            source_id=str(source_id or ""),
            source_name=str(source_name or ""),
            input_digest=str(input_digest or ""),
            prompt_version=str(prompt_version or ""),
            model=str(model or ""),
            plan_json=json.dumps(plan, ensure_ascii=False),
            created_at=now_iso(),
        )
        session.add(row)
        session.flush()
        return _plan_extraction_to_dict(row)


def source_audits_by_key(keys: list[str]) -> dict[str, dict]:
    """I verdetti del revisore gia' pagati, fra quelli chiesti.

    Una query per tutto il confronto, non una per fonte, per la stessa ragione
    dei piani parziali.

    Args:
        keys: Le chiavi degli artefatti, non affidabili.

    Returns:
        I verdetti trovati, per chiave, come dizionari grezzi dell'agente.

    Sola lettura, dentro il tenant corrente.
    """
    wanted = [key for key in dict.fromkeys(keys) if key]
    if not wanted:
        return {}
    with workspace_connection() as session:
        rows = (
            session.execute(
                select(WorkspaceSourceAudit)
                .where(WorkspaceSourceAudit.tenant_id == tenant_id())
                .where(WorkspaceSourceAudit.artifact_key.in_(wanted))
            )
            .scalars()
            .all()
        )
        return {row.artifact_key: json.loads(row.verdict_json or "{}") for row in rows}


def save_source_audit(
    *,
    artifact_key: str,
    verdict: dict,
    source_id: str = "",
    source_name: str = "",
    prompt_version: str = "",
    model: str = "",
) -> None:
    """Registra il verdetto del revisore su una fonte, una volta sola.

    Come per il piano parziale: la chiave contiene tutto cio' che determina il
    verdetto, quindi se c'e' gia' si tiene quello, e due confronti in gara sulla
    stessa fonte non si pestano.

    Raises:
        ValueError: Se la chiave e' vuota.
    """
    key = str(artifact_key or "").strip()
    if not key:
        raise ValueError("Un verdetto del revisore senza chiave non si ritrova.")

    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        existing = (
            session.execute(
                select(WorkspaceSourceAudit.id)
                .where(WorkspaceSourceAudit.tenant_id == current_tenant_id)
                .where(WorkspaceSourceAudit.artifact_key == key)
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return
        session.add(
            WorkspaceSourceAudit(
                tenant_id=current_tenant_id,
                artifact_key=key,
                source_id=str(source_id or ""),
                source_name=str(source_name or ""),
                prompt_version=str(prompt_version or ""),
                model=str(model or ""),
                verdict_json=json.dumps(verdict, ensure_ascii=False),
                created_at=now_iso(),
            )
        )
        session.flush()


def enqueue_plan_materialization(
    process_id: str | None,
    *,
    reason: str = "",
    session=None,
) -> dict | None:
    """Segna che il piano di questo processo va ricostruito.

    Non e' una scrittura sul processo: e' la registrazione di un lavoro da fare,
    e per questo non passa da `assert_write_allowed`. Salvare un'intervista e'
    permesso in ogni modalita' di chat, e una modalita' che permette di
    raccogliere evidenza ma non di prenderne nota lascerebbe il piano indietro
    senza che nessuno lo sappia.

    Una riga per processo. Se ce n'e' gia' una in attesa, `requested_at` si
    sposta in avanti e i tentativi ripartono: una fonte nuova rende di nuovo
    utile un lavoro che aveva fallito.

    Args:
        process_id: Il processo la cui evidenza e' cambiata; `None` non fa nulla
            (una fonte di progetto non appartiene a nessun processo).
        reason: Perche', per chi legge la coda.
        session: La sessione della scrittura che ha cambiato l'evidenza, quando
            c'e'. Passarla tiene coda e fonte nella stessa transazione: se il
            salvataggio della fonte torna indietro, la richiesta di
            ricostruzione torna indietro con lui.

    Returns:
        La riga di coda, o `None` se non c'era niente da mettere in coda.
    """
    if not process_id:
        return None

    def _upsert(active_session) -> dict:
        now = now_iso()
        current_tenant_id = tenant_id()
        row = (
            active_session.execute(
                select(WorkspacePlanMaterialization)
                .where(WorkspacePlanMaterialization.tenant_id == current_tenant_id)
                .where(WorkspacePlanMaterialization.process_id == process_id)
            )
            .scalars()
            .first()
        )
        if row is None:
            row = WorkspacePlanMaterialization(
                tenant_id=current_tenant_id,
                process_id=process_id,
                status="pending",
                requested_at=now,
                reason=reason,
                attempts=0,
                next_attempt_at=now,
            )
            active_session.add(row)
        else:
            row.status = "pending"
            row.requested_at = now
            row.reason = reason or row.reason
            row.attempts = 0
            row.next_attempt_at = now
            row.last_error = None
            row.completed_at = None
        active_session.flush()
        return _materialization_to_dict(row)

    if session is not None:
        return _upsert(session)

    with workspace_connection() as owned_session:
        return _upsert(owned_session)


def due_plan_materializations(limit: int = 5, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le richieste pronte, di tutti i tenant.

    Il worker gira fuori da una richiesta HTTP e quindi fuori da un tenant: la
    riga porta il proprio, e chi la lavora lo vincola prima di toccare il
    processo. Le piu' vecchie per prime, cosi' una richiesta non resta indietro
    perche' un altro processo continua a ricevere fonti.

    Non e' una lettura: le righe vengono prese in carico (`FOR UPDATE SKIP
    LOCKED` + scadenza spostata in avanti). Due worker - due istanze dell'app,
    o un worker separato accanto all'app - altrimenti sintetizzerebbero lo stesso
    piano due volte, e il processo si troverebbe due versioni nate dallo stesso
    evento.

    Args:
        limit: Quante righe prendere in carico.
        only_tenant_id: Limita la coda a un tenant. I test drenano cosi': una
            passata che prende la riga di un altro workspace lavorerebbe il
            processo di un cliente.

    Side effects:
        Sposta `next_attempt_at` di ogni riga presa in carico.
    """
    now = now_iso()
    lease_until = (
        datetime.now(UTC) + timedelta(seconds=MATERIALIZATION_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspacePlanMaterialization)
            .where(WorkspacePlanMaterialization.status == "pending")
            .where(WorkspacePlanMaterialization.next_attempt_at <= now)
            .order_by(WorkspacePlanMaterialization.next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(
                WorkspacePlanMaterialization.tenant_id == only_tenant_id
            )
        rows = session.execute(statement).scalars().all()
        claimed = [_materialization_to_dict(row) for row in rows]
        for row in rows:
            row.next_attempt_at = lease_until
        session.flush()
        return claimed


def _owned_materialization(session, materialization_id: int):
    """La riga di coda, se appartiene al tenant vincolato adesso.

    Il worker lavora righe di tenant diversi e l'id da solo non dice di chi sia:
    chiudere una riga senza guardare il tenant e' una scrittura fuori confine
    anche quando l'id viene dalla coda stessa, perche' fa dipendere l'isolamento
    dall'ordine delle chiamate invece che da un controllo.
    """
    row = session.get(WorkspacePlanMaterialization, materialization_id)
    if row is None or row.tenant_id != tenant_id():
        return None
    return row


def complete_plan_materialization(
    materialization_id: int,
    *,
    action: str,
    plan_version: int | None,
) -> dict | None:
    """La richiesta e' stata lavorata: cosa ne e' uscito resta scritto."""
    with workspace_connection() as session:
        row = _owned_materialization(session, materialization_id)
        if row is None:
            return None
        row.status = "done"
        row.completed_at = now_iso()
        row.last_error = None
        row.last_action = action
        row.plan_version = plan_version
        session.flush()
        return _materialization_to_dict(row)


def fail_plan_materialization(
    materialization_id: int,
    *,
    error: str,
    max_attempts: int = MATERIALIZATION_MAX_ATTEMPTS,
    backoff_seconds: int = MATERIALIZATION_BACKOFF_SECONDS,
) -> dict | None:
    """Un tentativo non riuscito: si riprova piu' tardi, ma non per sempre.

    Un guasto momentaneo - il modello in rate limit, il database occupato - si
    supera aspettando; un piano che non si riesce a costruire non migliora al
    quinto tentativo, e tenerlo in coda nasconderebbe che quel processo non ha
    un piano.
    """
    with workspace_connection() as session:
        row = _owned_materialization(session, materialization_id)
        if row is None:
            return None
        row.attempts += 1
        row.last_error = str(error)[:2000]
        if row.attempts >= max_attempts:
            row.status = "failed"
            row.completed_at = now_iso()
        else:
            delay = backoff_seconds * (2 ** (row.attempts - 1))
            row.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
        session.flush()
        return _materialization_to_dict(row)


def plan_materialization_for(process_id: str) -> dict | None:
    """La richiesta di ricostruzione di questo processo, se c'e'."""
    with workspace_connection() as session:
        row = (
            session.execute(
                select(WorkspacePlanMaterialization)
                .where(WorkspacePlanMaterialization.tenant_id == tenant_id())
                .where(WorkspacePlanMaterialization.process_id == process_id)
            )
            .scalars()
            .first()
        )
        return _materialization_to_dict(row) if row else None


def plan_materialization_stats() -> dict[str, int]:
    """Quante richieste sono in attesa e quante hanno smesso di riprovare."""
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspacePlanMaterialization.status, func.count())
            .group_by(WorkspacePlanMaterialization.status)
        ).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0),
        "stuck": counts.get("failed", 0),
    }


def enqueue_stale_plan_materializations(
    limit: int = 50, *, only_tenant_id: str | None = None
) -> list[dict]:
    """Mette in coda i processi il cui piano descrive un altro set di fonti.

    La coda si riempiva solo quando una fonte veniva creata con un processo. Due
    strade la lasciavano vuota, e il piano indietro per sempre:

    - le fonti registrate prima che la coda esistesse (il processo Esaote: tre
      interviste agli atti, un piano V1 preparato dal titolo, nessuna riga in
      coda, sei bozze start -> end);
    - le fonti di progetto, che valgono per ogni processo del progetto ma non
      nominano un processo da mettere in coda.

    Qui si confronta, per ogni processo con fonti, il set su cui il piano e' nato
    con quello che c'e' adesso, usando la stessa identita' del registro
    dell'evidenza. Tutti i tenant: gira nel worker, e la riga porta il suo.

    Una riga `failed` non si rimette in coda: e' un piano che non si riesce a
    costruire, e riprovarlo a ogni passata nasconderebbe proprio quello. Una riga
    `pending` c'e' gia'.

    Args:
        limit: Quante righe mettere in coda al massimo in una passata.
        only_tenant_id: Limita lo sweep a un tenant (amministrazione, test).

    Returns:
        Le righe messe in coda.
    """
    from backend.graphs.process.nodes import source_set_identity
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    with workspace_connection() as session:
        statement = select(WorkspaceProcess).where(WorkspaceProcess.archived_at.is_(None))
        if only_tenant_id:
            statement = statement.where(WorkspaceProcess.tenant_id == only_tenant_id)
        processes = session.execute(statement).scalars().all()
        # Solo le colonne che servono all'identita' del set di fonti
        # (`source_set_identity`): caricare la riga intera portava in memoria il
        # testo estratto di ogni fonte di ogni tenant, a ogni passata.
        source_rows = select(
            WorkspaceSource.tenant_id,
            WorkspaceSource.id,
            WorkspaceSource.name,
            WorkspaceSource.project_id,
            WorkspaceSource.process_id,
            WorkspaceSource.content_hash,
        )
        review_rows = select(
            WorkspaceBpmnReview.tenant_id,
            WorkspaceBpmnReview.bpmn_model_id,
            WorkspaceBpmnReview.evidence_source_set_id,
        )
        queue_rows = select(
            WorkspacePlanMaterialization.tenant_id,
            WorkspacePlanMaterialization.process_id,
            WorkspacePlanMaterialization.status,
        )
        if only_tenant_id:
            source_rows = source_rows.where(WorkspaceSource.tenant_id == only_tenant_id)
            review_rows = review_rows.where(WorkspaceBpmnReview.tenant_id == only_tenant_id)
            queue_rows = queue_rows.where(WorkspacePlanMaterialization.tenant_id == only_tenant_id)
        sources_by_project: dict[tuple[str, str], list[dict]] = {}
        for source in session.execute(source_rows):
            sources_by_project.setdefault((source.tenant_id, source.project_id), []).append(
                {
                    "id": source.id,
                    "name": source.name,
                    "project_id": source.project_id,
                    "process_id": source.process_id,
                    "content_hash": source.content_hash or "",
                }
            )
        reviews = {
            (row.tenant_id, row.bpmn_model_id): row.evidence_source_set_id
            for row in session.execute(review_rows)
        }
        queue = {(row.tenant_id, row.process_id): row.status for row in session.execute(queue_rows)}

        stale: list[tuple[str, str]] = []
        for process in processes:
            key = (process.tenant_id, process.id)
            if queue.get(key) in {"pending", "failed"}:
                continue
            sources = [
                item
                for item in sources_by_project.get((process.tenant_id, process.project_id), [])
                if item.get("process_id") in {None, process.id}
            ]
            if not sources:
                continue
            recorded = reviews.get((process.tenant_id, process.bpmn_model_id))
            if recorded == source_set_identity(sources):
                continue
            stale.append(key)
            if len(stale) >= max(1, int(limit)):
                break

    queued: list[dict] = []
    for owner_tenant, process_id in stale:
        token = set_current_tenant_id(owner_tenant)
        try:
            row = enqueue_plan_materialization(
                process_id, reason="piano costruito su un set di fonti diverso da quello agli atti"
            )
        finally:
            reset_current_tenant_id(token)
        if row:
            queued.append(row)
    return queued
