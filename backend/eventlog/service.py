"""L'import di un event log su un processo, dall'upload ai KPI.

Tiene insieme lettura del file (``readers``), analisi (``analysis``),
persistenza (``storage``) e il BPMN corrente del processo. Le route lo
chiamano e traducono le eccezioni in codici HTTP; qui non c'e' HTTP.
"""

from __future__ import annotations

import hashlib

from backend.eventlog import storage
from backend.eventlog.analysis import Preview, analyze, preview
from backend.eventlog.bpmn_match import ModelElement
from backend.eventlog.readers import EventLogFileError, Table, read_table
from backend.schemas.eventlog import (
    ActivityMatchReportResponse,
    ApplyEventLogMappingRequest,
    EventLogAnalysisResponse,
    EventLogPreviewResponse,
    EventLogResponse,
    QualityReportResponse,
    UploadedEventLogResponse,
)
from backend.simulation.scenario_builder import parse_bpmn_for_simulation
from backend.workspace_database import get_bpmn_model, get_process
from backend.workspace_services.source_ingestion import MAX_FILE_BYTES

SUPPORTED_SUFFIXES = (".csv", ".tsv", ".txt", ".xes")


class EventLogTooLarge(ValueError):
    pass


class EventLogNotFound(LookupError):
    pass


class TemplateNotFound(LookupError):
    pass


def clean_filename(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(character for character in name if character.isprintable())[:255]
    return name or "event-log.csv"


def upload_event_log(
    process_id: str, filename: str, payload: bytes, delimiter: str | None = None
) -> UploadedEventLogResponse | None:
    """Legge il file, lo conserva sul processo e ne restituisce l'anteprima.

    ``None`` se il processo non esiste nel tenant.

    Raises:
        EventLogTooLarge: oltre il limite dei file caricati.
        EventLogFileError: il file non si legge come event log.
    """
    if len(payload) > MAX_FILE_BYTES:
        raise EventLogTooLarge(f"Il file supera {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not filename.lower().endswith(SUPPORTED_SUFFIXES):
        raise EventLogFileError("Formato non supportato: servono CSV o XES.")
    if delimiter is not None and filename.lower().endswith(".xes"):
        raise EventLogFileError("Un file XES non ha separatore.")
    table = read_table(filename, payload, delimiter)
    stored = storage.store_event_log(storage.NewEventLog(
        process_id=process_id,
        name=filename,
        format=table.format,
        delimiter=table.delimiter,
        content_hash=hashlib.sha256(payload).hexdigest(),
        payload=payload,
        columns=table.header,
        row_count=len(table.rows),
    ))
    if stored is None:
        return None
    log, created = stored
    return UploadedEventLogResponse(**log.model_dump(), created=created, preview=_preview_response(preview(table)))


def preview_event_log(event_log_id: str, delimiter: str | None = None) -> EventLogPreviewResponse:
    """L'anteprima del file con un altro separatore, senza cambiare nulla."""
    _log, table = _read(event_log_id, delimiter)
    return _preview_response(preview(table))


def apply_mapping(event_log_id: str, request: ApplyEventLogMappingRequest) -> EventLogAnalysisResponse:
    """Applica il mapping (o il template) al file e salva qualita', abbinamento e KPI.

    Raises:
        EventLogNotFound, TemplateNotFound: non esistono nel tenant.
        MappingError: il mapping cita colonne che il file non ha.
        ValueError: l'abbinamento cita elementi che il BPMN non ha.
    """
    log, table = _read(event_log_id, request.delimiter)
    template_id = request.template_id
    if template_id is not None:
        template = storage.get_template(template_id)
        if template is None:
            raise TemplateNotFound(template_id)
        mapping = template.mapping
    else:
        assert request.mapping is not None  # garantito dal validatore della richiesta
        mapping = request.mapping

    elements, bpmn_version_id = _model_elements(log.process_id)
    result = analyze(
        table,
        mapping,
        elements,
        confirmed_matches=request.activity_matches,
        source_name=log.name,
    )
    quality = result.quality
    saved = storage.save_analysis(event_log_id, storage.AnalysisRecord(
        delimiter=table.delimiter,
        mapping=mapping,
        template_id=template_id,
        activity_matches=request.activity_matches,
        bpmn_version_id=bpmn_version_id,
        quality=QualityReportResponse(
            rows_read=quality.rows_read,
            rows_excluded=quality.rows_excluded,
            events=quality.events,
            cases=quality.cases,
            activities=quality.activities,
            resources=quality.resources,
            period_start=quality.period_start,
            period_end=quality.period_end,
            events_without_start=quality.events_without_start,
            issues=[
                {
                    "code": issue.code,
                    "message": issue.message,
                    "count": issue.count,
                    "rows": issue.rows,
                    "excludes_rows": issue.excludes_rows,
                }
                for issue in quality.issues
            ],
        ),
        activities=ActivityMatchReportResponse(
            bpmn_version_id=bpmn_version_id,
            confirmed=request.activity_matches is not None,
            matches=[
                {"activity": m.activity, "events": m.events, "element_id": m.element_id, "reason": m.reason}
                for m in result.matches.matches
            ],
            unmatched_activities=list(result.matches.unmatched_activities),
            unobserved_elements=[
                {"element_id": e.element_id, "name": e.name} for e in result.matches.unobserved_elements
            ],
        ),
        summary=result.summary,
    ))
    if saved is None:
        # Cancellato fra la lettura e la scrittura.
        raise EventLogNotFound(event_log_id)
    return saved


def _read(event_log_id: str, delimiter: str | None) -> tuple[EventLogResponse, Table]:
    loaded = storage.load_event_log_file(event_log_id)
    if loaded is None:
        raise EventLogNotFound(event_log_id)
    log, payload = loaded
    if delimiter is not None and log.format == "xes":
        raise EventLogFileError("Un file XES non ha separatore.")
    return log, read_table(log.name, payload, delimiter or log.delimiter)


def _model_elements(process_id: str) -> tuple[list[ModelElement], int | None]:
    """Le attivita' del BPMN corrente del processo e la versione da cui vengono."""
    process = get_process(process_id)
    model = get_bpmn_model(process["bpmn_model_id"]) if process else None
    if model is None or not model.get("xml"):
        return [], None
    tasks, _gateways = parse_bpmn_for_simulation(model["xml"])
    return [ModelElement(task.id, task.name) for task in tasks], model.get("version_id")


def _preview_response(value: Preview) -> EventLogPreviewResponse:
    return EventLogPreviewResponse(
        format=value.format,
        delimiter=value.delimiter,
        columns=list(value.columns),
        row_count=value.row_count,
        sample_rows=[list(row) for row in value.sample_rows],
    )
