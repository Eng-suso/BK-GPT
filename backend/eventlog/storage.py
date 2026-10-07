"""Persistenza degli event log importati e dei template di mapping.

Ogni lettura e scrittura passa dal tenant corrente: un log o un template di un
altro tenant non esiste (``None``), come per il resto del workspace.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.eventlog.mapping import ColumnMapping
from backend.schemas.eventlog import (
    ActivityMatchReportResponse,
    EventLogAnalysisResponse,
    EventLogResponse,
    EventLogTemplateRef,
    EventLogTemplateResponse,
    QualityReportResponse,
)
from backend.workspace_database import now_iso, tenant_id, tenant_row
from backend.workspace_storage import (
    WorkspaceEventLog,
    WorkspaceEventLogPayload,
    WorkspaceEventLogTemplate,
    WorkspaceProcess,
    workspace_connection,
)


@dataclass(frozen=True, slots=True)
class NewEventLog:
    process_id: str
    name: str
    format: str
    delimiter: str | None
    content_hash: str
    payload: bytes
    columns: tuple[str, ...]
    row_count: int


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    delimiter: str | None
    mapping: ColumnMapping
    template_id: int | None
    activity_matches: dict[str, str | None] | None
    bpmn_version_id: int | None
    quality: QualityReportResponse
    activities: ActivityMatchReportResponse
    summary: dict[str, Any] | None


def process_exists(process_id: str) -> bool:
    with workspace_connection() as session:
        return tenant_row(session, WorkspaceProcess, process_id) is not None


def store_event_log(upload: NewEventLog) -> tuple[EventLogResponse, bool] | None:
    """Registra il file sul processo. Lo stesso file gia' caricato ritrova la sua riga.

    Ritorna ``(log, creato)``, o ``None`` se il processo non e' del tenant. Un
    file ricaricato con un separatore diverso lo aggiorna, e il mapping
    applicato con il separatore vecchio non vale piu': il log torna ``uploaded``.
    """
    try:
        with workspace_connection() as session:
            if tenant_row(session, WorkspaceProcess, upload.process_id) is None:
                return None
            existing = _by_hash(session, upload.process_id, upload.content_hash)
            if existing is not None:
                if existing.delimiter != upload.delimiter:
                    existing.delimiter = upload.delimiter
                    existing.columns_json = json.dumps(list(upload.columns))
                    existing.row_count = upload.row_count
                    _clear_analysis(existing)
                return _log_response(session, existing), False
            row = WorkspaceEventLog(
                id=f"elog_{uuid.uuid4().hex}",
                tenant_id=tenant_id(),
                process_id=upload.process_id,
                name=upload.name,
                format=upload.format,
                delimiter=upload.delimiter,
                content_hash=upload.content_hash,
                byte_size=len(upload.payload),
                row_count=upload.row_count,
                columns_json=json.dumps(list(upload.columns)),
                status="uploaded",
                created_at=now_iso(),
            )
            session.add(row)
            session.flush()
            session.add(WorkspaceEventLogPayload(event_log_id=row.id, tenant_id=row.tenant_id, payload=upload.payload))
            session.flush()
            return _log_response(session, row), True
    except IntegrityError:
        # Due caricamenti dello stesso file insieme: ha vinto l'altro, e la sua
        # riga e' quella giusta.
        with workspace_connection() as session:
            existing = _by_hash(session, upload.process_id, upload.content_hash)
            if existing is None:
                raise
            return _log_response(session, existing), False


def list_event_logs(process_id: str) -> list[EventLogResponse] | None:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceProcess, process_id) is None:
            return None
        rows = session.execute(
            select(WorkspaceEventLog)
            .where(WorkspaceEventLog.tenant_id == tenant_id())
            .where(WorkspaceEventLog.process_id == process_id)
            .order_by(WorkspaceEventLog.created_at.desc(), WorkspaceEventLog.id)
        ).scalars().all()
        return [_log_response(session, row) for row in rows]


def get_event_log(event_log_id: str) -> EventLogResponse | None:
    with workspace_connection() as session:
        row = tenant_row(session, WorkspaceEventLog, event_log_id)
        return _log_response(session, row) if row is not None else None


def load_event_log_file(event_log_id: str) -> tuple[EventLogResponse, bytes] | None:
    with workspace_connection() as session:
        row = tenant_row(session, WorkspaceEventLog, event_log_id)
        if row is None:
            return None
        payload = session.get(WorkspaceEventLogPayload, event_log_id)
        if payload is None:
            # La riga senza il suo file e' uno stato che nessun percorso scrive.
            raise RuntimeError(f"event log {event_log_id} senza file")
        return _log_response(session, row), payload.payload


def save_analysis(event_log_id: str, record: AnalysisRecord) -> EventLogAnalysisResponse | None:
    with workspace_connection() as session:
        row = tenant_row(session, WorkspaceEventLog, event_log_id)
        if row is None:
            return None
        row.delimiter = record.delimiter
        row.status = "mapped"
        row.mapping_json = record.mapping.model_dump_json()
        row.template_id = record.template_id
        row.activity_matches_json = (
            json.dumps(record.activity_matches) if record.activity_matches is not None else None
        )
        row.bpmn_version_id = record.bpmn_version_id
        row.quality_json = record.quality.model_dump_json()
        row.match_json = record.activities.model_dump_json()
        row.summary_json = json.dumps(record.summary) if record.summary is not None else None
        row.mapped_at = now_iso()
        session.flush()
        return _analysis_response(session, row)


def get_analysis(event_log_id: str) -> EventLogAnalysisResponse | None:
    """L'esito dell'ultimo mapping. ``None`` anche per un log mai mappato: il
    chiamante distingue con ``get_event_log``."""
    with workspace_connection() as session:
        row = tenant_row(session, WorkspaceEventLog, event_log_id)
        if row is None or row.status != "mapped":
            return None
        return _analysis_response(session, row)


def delete_event_log(event_log_id: str) -> bool:
    with workspace_connection() as session:
        row = tenant_row(session, WorkspaceEventLog, event_log_id)
        if row is None:
            return False
        payload = session.get(WorkspaceEventLogPayload, event_log_id)
        if payload is not None:
            session.delete(payload)
        session.delete(row)
        return True


# --------------------------------------------------------------------------- #
# Template di mapping
# --------------------------------------------------------------------------- #


def save_template(
    *, name: str, mapping: ColumnMapping, columns: list[str], template_key: str | None
) -> EventLogTemplateResponse | None:
    """Una versione nuova del template; ``None`` se ``template_key`` non esiste nel tenant."""
    with workspace_connection() as session:
        if template_key is None:
            key, version = f"tmpl_{uuid.uuid4().hex}", 1
        else:
            latest = session.execute(
                select(func.max(WorkspaceEventLogTemplate.version))
                .where(WorkspaceEventLogTemplate.tenant_id == tenant_id())
                .where(WorkspaceEventLogTemplate.template_key == template_key)
            ).scalar_one()
            if latest is None:
                return None
            key, version = template_key, latest + 1
        row = WorkspaceEventLogTemplate(
            tenant_id=tenant_id(),
            template_key=key,
            version=version,
            name=name,
            mapping_json=mapping.model_dump_json(),
            columns_json=json.dumps(columns),
            created_at=now_iso(),
        )
        session.add(row)
        session.flush()
        return _template_response(row)


def list_templates() -> list[EventLogTemplateResponse]:
    """L'ultima versione di ogni template del tenant, per nome."""
    with workspace_connection() as session:
        latest = (
            select(
                WorkspaceEventLogTemplate.template_key,
                func.max(WorkspaceEventLogTemplate.version).label("version"),
            )
            .where(WorkspaceEventLogTemplate.tenant_id == tenant_id())
            .group_by(WorkspaceEventLogTemplate.template_key)
            .subquery()
        )
        rows = session.execute(
            select(WorkspaceEventLogTemplate)
            .join(
                latest,
                (WorkspaceEventLogTemplate.template_key == latest.c.template_key)
                & (WorkspaceEventLogTemplate.version == latest.c.version),
            )
            .where(WorkspaceEventLogTemplate.tenant_id == tenant_id())
            .order_by(WorkspaceEventLogTemplate.name, WorkspaceEventLogTemplate.template_key)
        ).scalars().all()
        return [_template_response(row) for row in rows]


def template_versions(template_key: str) -> list[EventLogTemplateResponse]:
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceEventLogTemplate)
            .where(WorkspaceEventLogTemplate.tenant_id == tenant_id())
            .where(WorkspaceEventLogTemplate.template_key == template_key)
            .order_by(WorkspaceEventLogTemplate.version.desc())
        ).scalars().all()
        return [_template_response(row) for row in rows]


def get_template(template_id: int) -> EventLogTemplateResponse | None:
    with workspace_connection() as session:
        row = session.get(WorkspaceEventLogTemplate, template_id)
        if row is None or row.tenant_id != tenant_id():
            return None
        return _template_response(row)


# --------------------------------------------------------------------------- #
# Righe -> risposte
# --------------------------------------------------------------------------- #


def _by_hash(session: Session, process_id: str, content_hash: str) -> WorkspaceEventLog | None:
    return session.execute(
        select(WorkspaceEventLog)
        .where(WorkspaceEventLog.tenant_id == tenant_id())
        .where(WorkspaceEventLog.process_id == process_id)
        .where(WorkspaceEventLog.content_hash == content_hash)
    ).scalars().first()


def _clear_analysis(row: WorkspaceEventLog) -> None:
    row.status = "uploaded"
    row.mapping_json = None
    row.template_id = None
    row.activity_matches_json = None
    row.bpmn_version_id = None
    row.quality_json = None
    row.summary_json = None
    row.match_json = None
    row.mapped_at = None


def _log_response(session: Session, row: WorkspaceEventLog) -> EventLogResponse:
    template = session.get(WorkspaceEventLogTemplate, row.template_id) if row.template_id else None
    return EventLogResponse(
        id=row.id,
        process_id=row.process_id,
        name=row.name,
        format=row.format,
        delimiter=row.delimiter,
        byte_size=row.byte_size,
        row_count=row.row_count,
        columns=json.loads(row.columns_json),
        status=row.status,
        mapping=ColumnMapping.model_validate_json(row.mapping_json) if row.mapping_json else None,
        template=EventLogTemplateRef(
            id=template.id, template_key=template.template_key, version=template.version, name=template.name
        ) if template is not None else None,
        created_at=row.created_at,
        mapped_at=row.mapped_at,
    )


def _analysis_response(session: Session, row: WorkspaceEventLog) -> EventLogAnalysisResponse:
    if row.quality_json is None or row.match_json is None:
        raise RuntimeError(f"event log {row.id} mappato senza esito")
    return EventLogAnalysisResponse(
        event_log=_log_response(session, row),
        quality=QualityReportResponse.model_validate_json(row.quality_json),
        activities=ActivityMatchReportResponse.model_validate_json(row.match_json),
        summary=json.loads(row.summary_json) if row.summary_json else None,
    )


def _template_response(row: WorkspaceEventLogTemplate) -> EventLogTemplateResponse:
    return EventLogTemplateResponse(
        id=row.id,
        template_key=row.template_key,
        version=row.version,
        name=row.name,
        mapping=ColumnMapping.model_validate_json(row.mapping_json),
        columns=json.loads(row.columns_json),
        created_at=row.created_at,
    )
