"""Fonti di progetto e cliente: registrazione, acquisizione in coda, verifica,
ruoli e scarto.

Una fonte nuova o approvata rimette in coda il piano dei processi che informa.
La chiamata passa da `plans.enqueue_plan_materialization` e non da un nome
importato, cosi' chi sostituisce quella funzione nel modulo `plans` (un test
che simula un guasto dopo l'inserimento in coda) la sostituisce anche qui.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, or_, select

from backend.workspace_database import plans
from backend.workspace_database._common import now_iso, slugify, tenant_id, tenant_row, unique_id
from backend.workspace_storage import (
    WorkspaceClient,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceEvidenceSegment,
    WorkspaceSource,
    WorkspaceSourceEvidence,
    workspace_connection,
)


if TYPE_CHECKING:
    from backend.workspace_services.source_ingestion import ParsedSource


logger = logging.getLogger("backend.workspace_database")


def source_to_dict(source: WorkspaceSource) -> dict:
    def structured(raw: str | None) -> list:
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    return {
        "id": source.id,
        "project_id": source.project_id,
        "client_id": source.client_id,
        "process_id": source.process_id,
        "name": source.name,
        "type": source.type,
        "meta": source.meta,
        "roles": structured(source.roles_json),
        "retention": source.retention,
        "scopes": structured(source.scopes_json),
        "status": source.status,
        # Stringa vuota e non `None`: chi legge confronta impronte, e un `None`
        # fra due confronti si comporta in modo diverso da un testo assente.
        "content_hash": getattr(source, "content_hash", None) or "",
        "byte_size": source.byte_size,
        "mime_type": source.mime_type,
        "acquisition_status": source.acquisition_status,
        "acquisition_error": source.acquisition_error,
        "claims_status": source.claims_status,
        "claims_error": source.claims_error,
        "reconcile_status": source.reconcile_status,
    }


def list_project_sources(project_id: str, *, include_client: bool = False) -> list[dict]:
    """Le fonti di un progetto e, con `include_client`, quelle del suo cliente.

    Una fonte del cliente (P1.16) vale per tutti i suoi progetti: compare nelle
    Fonti di ognuno, con `project_id` vuoto, e nel contesto degli agenti. Il
    default resta il solo progetto: il set di fonti di un piano di processo non
    le legge ancora, e cambiarlo qui l'avrebbe cambiato in silenzio.
    """
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            return []

        owned = WorkspaceSource.project_id == project_id
        if include_client:
            owned = or_(
                owned,
                and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == project.client_id),
            )
        statement = (
            select(WorkspaceSource)
            .where(owned)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .order_by(WorkspaceSource.name)
        )
        sources = session.execute(statement).scalars().all()
        return [source_to_dict(source) for source in sources]


def list_client_sources(client_id: str) -> list[dict] | None:
    """Le fonti del cliente: quelle che valgono per tutti i suoi progetti.

    Returns:
        Le fonti, o `None` se il cliente non esiste in questo tenant.
    """
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceClient, client_id) is None:
            return None
        sources = session.execute(
            select(WorkspaceSource)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .where(WorkspaceSource.project_id.is_(None))
            .where(WorkspaceSource.client_id == client_id)
            .order_by(WorkspaceSource.name)
        ).scalars().all()
        return [source_to_dict(source) for source in sources]


def get_project_source(source_id: str) -> dict | None:
    """La fonte, per id, dentro il tenant corrente.

    Args:
        source_id: Id della fonte, non affidabile.

    Returns:
        Il record della fonte, o ``None`` se non esiste in questo tenant.

    Sola lettura.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        return source_to_dict(source) if source is not None else None


def get_project_source_record(source_id: str) -> WorkspaceSource | None:
    """Restituisce una copia staccata della fonte, sempre limitata al tenant."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        session.expunge(source)
        return source


def _assert_source_scope(project_id: str, process_id: str | None) -> None:
    """Una fonte non puo' essere registrata fuori dallo scope del turno.

    L'evidenza raccolta in chat ha due destinazioni: la memoria episodica e il
    pannello Fonti. Isolare solo la prima lascerebbe il buco piu' visibile dei
    due - l'evidenza finisce nel processo giusto, ma la fonte compare nel
    pannello di un altro incarico, dove qualcuno la aprira' credendola sua.
    Qui il vincolo vale prima della scrittura, per ogni chiamante: il tool
    `save_process_evidence` deriva il progetto dal process_id che gli passa
    l'LLM, quindi controllare il solo progetto non basterebbe.

    No-op fuori da un agent run (worker, cutover, test).
    """
    from backend.agents.scope_guard import assert_process_in_scope, assert_project_in_scope

    assert_project_in_scope(project_id)
    assert_process_in_scope(process_id)


def _enqueue_plans_touched_by_source(
    session,
    *,
    project_id: str,
    process_id: str | None,
    tenant: str,
    reason: str,
) -> None:
    """Mette in coda i piani che questa fonte rende da rifare.

    Una fonte di progetto vale per ogni processo del progetto - e' cosi' che il
    registro dell'evidenza la legge - quindi il piano da rifare non e' uno solo.
    La coda si scrive nella stessa transazione della fonte: un piano da
    ricostruire che si perde perche' la transazione e' finita e' un piano che
    resta indietro in silenzio.
    """
    affected = (
        [process_id]
        if process_id
        else session.execute(
            select(WorkspaceProcess.id)
            .where(WorkspaceProcess.project_id == project_id)
            .where(WorkspaceProcess.tenant_id == tenant)
        )
        .scalars()
        .all()
    )
    for affected_process_id in affected:
        plans.enqueue_plan_materialization(affected_process_id, reason=reason, session=session)


def create_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
    content_hash: str = "",
) -> dict:
    _assert_source_scope(project_id, process_id)
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        if process_id:
            process = tenant_row(session, WorkspaceProcess, process_id)
            if process is None or process.project_id != project_id:
                raise ValueError(f"Processo non trovato: {process_id}")

        source_id = unique_id(session, WorkspaceSource, f"src-{slugify(name, 'source')}")
        source = WorkspaceSource(
            id=source_id,
            tenant_id=current_tenant_id,
            project_id=project_id,
            client_id=project.client_id,
            process_id=process_id,
            name=name.strip(),
            type=type.strip() or "Fonte",
            meta=meta.strip(),
            content_hash=content_hash.strip() or None,
        )
        session.add(source)
        session.flush()
        # La conoscenza del processo e' cambiata: il piano che descrive il
        # processo senza questa fonte e' da rifare. Va in coda qui, nella stessa
        # transazione della fonte, invece di essere ricostruito quando qualcuno
        # chiede di disegnare - che e' il momento in cui nessuno puo' aspettare.
        _enqueue_plans_touched_by_source(
            session,
            project_id=project_id,
            process_id=process_id,
            tenant=current_tenant_id,
            reason=f"fonte registrata: {source.name}",
        )
        return source_to_dict(source)


def process_id_for_identity(scopes: list[dict[str, str]]) -> str:
    """Il processo a cui un caricamento appartiene, per la sua identita'."""
    process_ids = sorted({item["id"].strip() for item in scopes if item.get("type") == "process"})
    return process_ids[0] if len(process_ids) == 1 else ""


def create_ingested_source(
    *,
    project_id: str | None = None,
    client_id: str | None = None,
    name: str,
    roles: list[str],
    retention: str,
    scopes: list[dict[str, str]],
    content_hash: str,
    byte_size: int,
    mime_type: str,
    storage_key: str,
) -> tuple[dict, bool]:
    """Registra una fonte caricata e la mette in coda per l'acquisizione.

    Il file e' gia' conservato (`storage_key`); leggerlo - layout, tabelle, OCR -
    lo fa `source_worker`, fuori dalla richiesta. Fino ad allora la fonte esiste
    ma non ha testo, e lo dice: `acquisition_status == "pending"`.

    Una fonte appartiene a un progetto (`project_id`) o al cliente
    (`client_id`, P1.16): quella del cliente vale per tutti i suoi progetti, non
    ha processo, e il suo ambito e' il cliente.
    """
    if (project_id is None) == (client_id is None):
        raise ValueError("Una fonte appartiene a un progetto o a un cliente, non a entrambi.")
    if client_id is not None:
        scopes = [{"type": "client", "id": client_id}]
    role_order = {name: index for index, name in enumerate(
        ("context", "process_evidence", "policy", "operational_data")
    )}
    scope_order = {"client": 0, "project": 1, "process": 2}
    role_values = sorted(set(roles), key=role_order.__getitem__)
    scopes_value = sorted(
        ({"type": scope_type, "id": scope_id} for scope_type, scope_id in {
            (item["type"], item["id"].strip()) for item in scopes
        }),
        key=lambda item: (scope_order[item["type"]], item["id"]),
    )
    roles_json = json.dumps(role_values, ensure_ascii=False, separators=(",", ":"))
    scopes_json = json.dumps(scopes_value, ensure_ascii=False, separators=(",", ":"))
    # L'identita' di un file caricato e' il suo contenuto, nel progetto e nel
    # processo a cui appartiene: i ruoli sono attributi che si cambiano, non
    # un'altra fonte. Prima entravano nella chiave, e lo stesso file con un
    # ruolo diverso diventava un doppione. Il processo invece resta: una fonte
    # appartiene a un solo processo, e lo stesso file portato in un altro
    # processo e' evidenza di quell'altro.
    ingestion_key = hashlib.sha256(
        f"file:{content_hash}:{process_id_for_identity(scopes)}".encode()
    ).hexdigest()
    process_ids = [item["id"] for item in scopes_value if item["type"] == "process"]
    # Con due processi la fonte finirebbe a livello di progetto (`process_id`
    # vuoto) e diventerebbe evidenza anche per un terzo processo che non c'entra.
    if len(process_ids) > 1:
        raise ValueError("Una fonte caricata appartiene a un solo processo.")
    process_id = process_ids[0] if process_ids else None
    if project_id is not None:
        _assert_source_scope(project_id, process_id)
        validate_source_scopes(project_id, scopes_value)

    with workspace_connection() as session:
        if project_id is not None:
            project = tenant_row(session, WorkspaceProject, project_id)
            if project is None:
                raise ValueError(f"Progetto non trovato: {project_id}")
            owner_client_id = project.client_id
            owned = WorkspaceSource.project_id == project_id
        else:
            if tenant_row(session, WorkspaceClient, client_id) is None:
                raise ValueError(f"Cliente non trovato: {client_id}")
            owner_client_id = client_id
            owned = and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == client_id)
        lock_key = int(ingestion_key[:16], 16)
        if lock_key >= 2**63:
            lock_key -= 2**64
        session.execute(select(func.pg_advisory_xact_lock(lock_key)))
        # Per contenuto e non per chiave: le fonti caricate prima di questa
        # regola hanno una chiave calcolata anche sui ruoli. Fra due doppioni
        # gia' esistenti vale il primo.
        existing = session.execute(
            select(WorkspaceSource)
            .where(WorkspaceSource.tenant_id == tenant_id())
            .where(owned)
            .where(WorkspaceSource.content_hash == content_hash)
            .where(WorkspaceSource.storage_key.is_not(None))
            .where(
                WorkspaceSource.process_id == process_id
                if process_id
                else WorkspaceSource.process_id.is_(None)
            )
            .order_by(WorkspaceSource.id)
        ).scalars().first()
        if existing is not None:
            # Ricaricare un file che non era stato letto e' il modo naturale di
            # dire "riprova": la fonte torna in coda invece di restare morta.
            if existing.acquisition_status == "failed":
                existing.acquisition_status = "pending"
                existing.acquisition_attempts = 0
                existing.acquisition_error = None
                existing.acquisition_next_attempt_at = now_iso()
                existing.meta = "In lettura: testo ed evidenze arrivano tra poco."
                session.flush()
            return source_to_dict(existing), False

        source = WorkspaceSource(
            id=unique_id(session, WorkspaceSource, f"src-{slugify(name, 'source')}"),
            tenant_id=tenant_id(),
            project_id=project_id,
            client_id=owner_client_id,
            process_id=process_id,
            name=name.strip(),
            type="File",
            meta="In lettura: testo ed evidenze arrivano tra poco.",
            roles_json=roles_json,
            retention=retention,
            scopes_json=scopes_json,
            status="extracted",
            content_hash=content_hash,
            byte_size=byte_size,
            mime_type=mime_type,
            storage_key=storage_key,
            ingestion_key=ingestion_key,
            acquisition_status="pending",
            acquisition_attempts=0,
            acquisition_next_attempt_at=now_iso(),
        )
        session.add(source)
        session.flush()
        return source_to_dict(source), True


ACQUISITION_MAX_ATTEMPTS = 4


ACQUISITION_BACKOFF_SECONDS = 30


# Un PDF lungo con OCR resta in lettura per minuti: il lease copre la
# conversione piu' lenta attesa, non la media. Se chi l'ha presa muore, la
# fonte torna eleggibile da sola.
ACQUISITION_LEASE_SECONDS = 1200


def due_source_acquisitions(limit: int = 2, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti da leggere, di tutti i tenant.

    Come `due_plan_materializations`: `FOR UPDATE SKIP LOCKED` e scadenza spostata
    in avanti, cosi' due worker non leggono lo stesso file.

    Returns:
        Per ogni fonte: id, tenant, nome, storage_key e hash del contenuto.
    """
    now = now_iso()
    lease_until = (
        datetime.now(UTC) + timedelta(seconds=ACQUISITION_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.acquisition_status == "pending")
            .where(WorkspaceSource.acquisition_next_attempt_at <= now)
            .order_by(WorkspaceSource.acquisition_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        rows = session.execute(statement).scalars().all()
        claimed = []
        for row in rows:
            # Il tentativo si conta alla presa in carico, non all'esito: un file
            # che fa morire il worker (memoria, processo ucciso) non arriva mai a
            # `fail_source_acquisition`, e senza questo tornerebbe in lettura a
            # ogni scadenza del lease, per sempre.
            if row.acquisition_attempts >= ACQUISITION_MAX_ATTEMPTS:
                row.acquisition_status = "failed"
                row.acquisition_next_attempt_at = None
                row.acquisition_error = row.acquisition_error or "La lettura si e' interrotta troppe volte."
                row.meta = f"Non leggibile: {row.acquisition_error}"[:2000]
                continue
            row.acquisition_attempts += 1
            row.acquisition_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "storage_key": row.storage_key,
                    "content_hash": row.content_hash,
                    "process_id": row.process_id,
                }
            )
        session.flush()
        return claimed


def complete_source_acquisition(source_id: str, parsed: "ParsedSource") -> dict | None:
    """Scrive il risultato della lettura: testo, evidenze ancorate, esito.

    `parsed` e' un `ParsedSource` di `source_ingestion`. Le evidenze precedenti
    della fonte vengono sostituite, non affiancate: descrivono lo stesso file.
    """
    evidence = parsed.evidence
    status = "partial" if evidence is not None and evidence.status == "partial" else "done"
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        source.extracted_text = parsed.text
        source.parser = parsed.parser
        source.acquisition_status = status
        source.acquisition_error = None
        source.acquisition_next_attempt_at = None
        if source.confirm_when_read and source.status != "approved":
            # Era partito in chat mentre era in lettura: la conferma scatta ora.
            _approve_source(session, source, reason=f"fonte inviata in chat: {source.name}")
        if status == "partial":
            missing = "; ".join(
                issue.message for issue in evidence.issues if issue.severity == "partial"
            )
            source.meta = f"Acquisizione parziale: {missing}"[:2000]
        else:
            source.meta = "Testo ed evidenze pronti per la consultazione."

        session.execute(
            delete(WorkspaceEvidenceSegment).where(WorkspaceEvidenceSegment.source_id == source_id)
        )
        session.execute(
            delete(WorkspaceSourceEvidence).where(WorkspaceSourceEvidence.source_id == source_id)
        )
        if evidence is not None:
            payload = evidence.to_dict()
            session.add(
                WorkspaceSourceEvidence(
                    source_id=source_id,
                    tenant_id=source.tenant_id,
                    schema_version=payload["schema_version"],
                    format=payload["format"],
                    parser=payload["parser"],
                    status=payload["status"],
                    content_hash=parsed.content_hash,
                    structure_json=json.dumps(payload["structure"], ensure_ascii=False),
                    issues_json=json.dumps(payload["issues"], ensure_ascii=False),
                    acquired_at=now_iso(),
                )
            )
            session.add_all(
                WorkspaceEvidenceSegment(
                    tenant_id=source.tenant_id,
                    source_id=source_id,
                    ordinal=ordinal,
                    anchor_kind=segment["anchor"]["kind"],
                    anchor_ref=segment["anchor"]["ref"],
                    locator_json=json.dumps(segment["anchor"]["locator"], ensure_ascii=False),
                    # PostgreSQL rifiuta il byte NUL nelle colonne di testo; un
                    # PDF o un foglio possono contenerlo.
                    text=segment["text"].replace("\x00", ""),
                    value_type=segment["value_type"],
                    value_json=json.dumps(segment["value"], ensure_ascii=False),
                    attributes_json=json.dumps(segment["attributes"], ensure_ascii=False),
                )
                for ordinal, segment in enumerate(payload["segments"])
            )
        session.flush()
        return source_to_dict(source)


def fail_source_acquisition(
    source_id: str,
    *,
    error: str,
    permanent: bool,
    max_attempts: int = ACQUISITION_MAX_ATTEMPTS,
    backoff_seconds: int = ACQUISITION_BACKOFF_SECONDS,
) -> dict | None:
    """Una lettura non riuscita.

    `permanent`: il file non e' leggibile (formato, password, XML non sicuro),
    riprovare dara' lo stesso esito. Altrimenti (servizio giu', timeout) si
    riprova con backoff, ma non per sempre.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        # Il tentativo e' gia' stato contato alla presa in carico.
        source.acquisition_error = str(error)[:2000]
        if permanent or source.acquisition_attempts >= max_attempts:
            source.acquisition_status = "failed"
            source.acquisition_next_attempt_at = None
            source.meta = f"Non leggibile: {error}"[:2000]
        else:
            delay = backoff_seconds * (2 ** (source.acquisition_attempts - 1))
            source.acquisition_next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
        session.flush()
        return source_to_dict(source)


class SourceNotVerifiable(ValueError):
    """La fonte non si puo' ancora usare come evidenza (in lettura o illeggibile)."""


def update_source_roles(source_id: str, roles: list[str]) -> dict | None:
    """Cambia a cosa serve una fonte. Non cambia quale fonte e'.

    Returns:
        La fonte aggiornata, o `None` se non c'e' in questo tenant.
    """
    role_order = {name: index for index, name in enumerate(
        ("context", "process_evidence", "policy", "operational_data")
    )}
    values = sorted(set(roles), key=role_order.__getitem__)
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        source.roles_json = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        session.flush()
        return source_to_dict(source)


def verify_project_source(source_id: str) -> dict | None:
    """Il consulente ha controllato il file: da adesso e' evidenza del processo.

    Un file caricato entra nel registro dell'evidenza solo dopo questa conferma
    (`status == "approved"`): il testo estratto da un parser non e' ancora una
    fonte che il consulente ha fatto propria. Come per una fonte registrata dalla
    chat, i piani dei processi che la fonte tocca vanno ricostruiti.

    Raises:
        SourceNotVerifiable: la lettura non e' finita o non e' riuscita.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        if source.storage_key and source.acquisition_status not in {"done", "partial"}:
            raise SourceNotVerifiable(
                "La fonte non è ancora stata letta: si può usare come evidenza quando la lettura è finita."
            )
        if source.status == "approved":
            return source_to_dict(source)
        _approve_source(session, source, reason=f"fonte verificata: {source.name}")
        session.flush()
        return source_to_dict(source)


def _approve_source(session: Any, source: WorkspaceSource, *, reason: str) -> None:
    """La fonte diventa evidenza: piani da ricostruire, affermazioni da estrarre.

    Il chiamante ha gia' controllato che la lettura sia finita.
    """
    source.status = "approved"
    source.confirm_when_read = False
    if source.process_id:
        affected = [source.process_id]
    elif source.project_id:
        affected = list(
            session.execute(
                select(WorkspaceProcess.id)
                .where(WorkspaceProcess.project_id == source.project_id)
                .where(WorkspaceProcess.tenant_id == source.tenant_id)
            ).scalars().all()
        )
    else:
        # Una fonte del cliente (P1.16) non e' ancora nel set di fonti dei
        # piani: confermarla non li rende vecchi.
        affected = []
    for affected_process_id in affected:
        plans.enqueue_plan_materialization(affected_process_id, reason=reason, session=session)
    if source.storage_key and source.claims_status != "done":
        # P1.12: l'estrazione delle affermazioni parte da un gesto del
        # consulente - questa conferma - e mai da sola.
        source.claims_status = "pending"
        source.claims_attempts = 0
        source.claims_error = None
        source.claims_next_attempt_at = now_iso()


def confirm_sources_sent_in_chat(source_ids: list[str]) -> list[str]:
    """Mandare un file in chat vale come confermarlo.

    Un file gia' letto diventa evidenza subito; uno ancora in lettura lo
    diventa quando la lettura finisce (`confirm_when_read`). Uno non leggibile
    resta com'e'.

    Returns:
        Gli id delle fonti confermate adesso.
    """
    confirmed: list[str] = []
    with workspace_connection() as session:
        for source_id in dict.fromkeys(source_ids):
            source = tenant_row(session, WorkspaceSource, source_id)
            if source is None or not source.storage_key or source.status == "approved":
                continue
            if source.acquisition_status in {"done", "partial"}:
                _approve_source(session, source, reason=f"fonte inviata in chat: {source.name}")
                confirmed.append(source.id)
            elif source.acquisition_status == "pending":
                source.confirm_when_read = True
        session.flush()
    return confirmed


class SourceNotDiscardable(ValueError):
    """La fonte non si scarta: e' gia' evidenza del processo, o non e' un file caricato."""


def discard_uploaded_source(source_id: str) -> bool:
    """Scarta un file caricato che nessuno ha ancora fatto proprio.

    E' la regola della card nel composer: un file nuovo, caricato dalla chat e
    tolto prima dell'invio, non resta tra le Fonti. Una fonte confermata come
    evidenza (`status == "approved"`) o creata dalla chat senza file non si
    scarta da qui. Le evidenze della fonte cadono con lei (FK in cascata);
    l'originale su disco si toglie solo se nessun'altra fonte lo usa.

    Returns:
        `False` se la fonte non esiste nel tenant.

    Raises:
        SourceNotDiscardable: la fonte e' gia' evidenza o non ha un file.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return False
        if not source.storage_key or source.status == "approved":
            raise SourceNotDiscardable(
                "Questa fonte non si scarta da qui: e' gia' evidenza del processo o non e' un file caricato."
            )
        storage_key = source.storage_key
        session.execute(
            delete(WorkspaceEvidenceSegment).where(WorkspaceEvidenceSegment.source_id == source_id)
        )
        session.execute(
            delete(WorkspaceSourceEvidence).where(WorkspaceSourceEvidence.source_id == source_id)
        )
        session.delete(source)
        session.flush()
        still_used = session.execute(
            select(func.count())
            .select_from(WorkspaceSource)
            .where(WorkspaceSource.storage_key == storage_key)
        ).scalar_one()
    if not still_used:
        from backend.workspace_services.source_ingestion import SourceFileError, delete_original

        try:
            delete_original(storage_key)
        except (SourceFileError, OSError):
            logger.warning("originale %s non rimosso", storage_key, exc_info=True)
    return True


def source_acquisition_stats() -> dict[str, int]:
    """Quante fonti aspettano di essere lette e quante hanno smesso di riprovare."""
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceSource.acquisition_status, func.count())
            .where(WorkspaceSource.acquisition_status.is_not(None))
            .group_by(WorkspaceSource.acquisition_status)
        ).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "done": counts.get("done", 0) + counts.get("partial", 0),
        "stuck": counts.get("failed", 0),
    }


def validate_source_scopes(project_id: str, scopes: list[dict[str, str]]) -> None:
    """Impedisce che una fonte venga collegata a record di un altro incarico."""
    with workspace_connection() as session:
        project = tenant_row(session, WorkspaceProject, project_id)
        if project is None:
            raise ValueError(f"Progetto non trovato: {project_id}")
        for scope in scopes:
            if scope["type"] == "project" and scope["id"] != project_id:
                raise ValueError("L'ambito progetto non appartiene a questa fonte.")
            if scope["type"] == "client" and scope["id"] != project.client_id:
                raise ValueError("L'ambito cliente non appartiene a questo progetto.")
            if scope["type"] == "process":
                process = tenant_row(session, WorkspaceProcess, scope["id"])
                if process is None or process.project_id != project_id:
                    raise ValueError("Il processo scelto non appartiene a questo progetto.")


def ensure_project_source(
    project_id: str,
    name: str,
    type: str,
    meta: str = "",
    process_id: str | None = None,
    content_hash: str = "",
) -> tuple[dict, bool]:
    """Registra una fonte una volta sola, per nome, dentro il suo processo.

    Un'intervista salvata due volte dalla chat - il consulente riformula, il
    turno viene ripetuto - non deve diventare due voci nel pannello Fonti. Il
    record resta quello di prima: dice quando l'evidenza e' entrata nel
    progetto, e riscriverlo a ogni salvataggio cancellerebbe quel fatto.

    **Con una sola eccezione, ed e' il punto di questa funzione:** se il testo e'
    cambiato, la fonte non e' piu' la stessa fonte. L'impronta si aggiorna e i
    piani costruiti su di lei vanno in coda. Senza questo, un'intervista corretta
    e risalvata con lo stesso titolo lasciava l'identita' del set ferma, il piano
    risultava "costruito sulle fonti correnti" e continuava a descrivere il testo
    di prima: un piano indietro che nessun controllo poteva vedere.

    Args:
        project_id: Progetto proprietario, non affidabile.
        name: Nome della fonte come la legge il consulente, non affidabile.
        type: Etichetta del tipo, gia' tradotta per chi legge.
        meta: Nota in prosa sulla fonte.
        process_id: Processo a cui l'evidenza appartiene, quando c'e'.
        content_hash: L'impronta del testo salvato
            (`source_document.content_digest`). Vuota da chi il testo non ce
            l'ha: in quel caso l'impronta gia' registrata resta, perche'
            cancellarla direbbe "non si sa piu' cosa contiene" a proposito di
            una fonte che non e' cambiata.

    Returns:
        La fonte e se e' stata creata adesso (``False`` se esisteva gia', anche
        quando il suo testo e' stato aggiornato: la fonte non e' nuova).

    Raises:
        ValueError: Se il progetto non esiste o il processo non e' suo.
        ScopeViolation: Se progetto o processo non sono quelli autorizzati per
            il turno di chat corrente.

    Scrive nel workspace quando la fonte non esiste, o quando esiste e il suo
    testo e' cambiato.
    """
    _assert_source_scope(project_id, process_id)
    cleaned_name = name.strip()
    cleaned_hash = content_hash.strip()
    with workspace_connection() as session:
        current_tenant_id = tenant_id()
        if tenant_row(session, WorkspaceProject, project_id) is None:
            raise ValueError(f"Progetto non trovato: {project_id}")

        existing = (
            session.execute(
                select(WorkspaceSource)
                .where(WorkspaceSource.project_id == project_id)
                .where(WorkspaceSource.tenant_id == current_tenant_id)
                .where(WorkspaceSource.process_id == process_id)
                .where(func.lower(WorkspaceSource.name) == cleaned_name.lower())
            )
            .scalars()
            .first()
        )
        if existing is not None:
            if cleaned_hash and cleaned_hash != (existing.content_hash or ""):
                existing.content_hash = cleaned_hash
                session.flush()
                _enqueue_plans_touched_by_source(
                    session,
                    project_id=project_id,
                    process_id=process_id,
                    tenant=current_tenant_id,
                    reason=f"testo della fonte cambiato: {existing.name}",
                )
            return source_to_dict(existing), False

    return (
        create_project_source(
            project_id=project_id,
            name=cleaned_name,
            type=type,
            meta=meta,
            process_id=process_id,
            content_hash=cleaned_hash,
        ),
        True,
    )
