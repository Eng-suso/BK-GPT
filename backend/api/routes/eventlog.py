"""Import degli event log reali sui processi (SIM-15) e template di mapping."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from backend.eventlog import storage
from backend.eventlog.mapping import MappingError
from backend.eventlog.readers import EventLogFileError
from backend.eventlog.service import (
    EventLogNotFound,
    EventLogTooLarge,
    TemplateNotFound,
    apply_mapping,
    clean_filename,
    preview_event_log,
    upload_event_log,
)
from backend.schemas.eventlog import (
    ApplyEventLogMappingRequest,
    Delimiter,
    EventLogAnalysisResponse,
    EventLogPreviewResponse,
    EventLogResponse,
    EventLogTemplateResponse,
    SaveEventLogTemplateRequest,
    UploadedEventLogResponse,
)
from backend.security import require_principal
from backend.workspace_services.source_ingestion import MAX_FILE_BYTES

router = APIRouter(
    prefix="/v1/workspace",
    tags=["event-logs"],
    dependencies=[Depends(require_principal)],
)

_LOG_NOT_FOUND = "Event log non trovato."
_PROCESS_NOT_FOUND = "Processo non trovato."
_TEMPLATE_NOT_FOUND = "Template di mapping non trovato."


@router.post(
    "/processes/{process_id}/event-logs",
    response_model=UploadedEventLogResponse,
    status_code=201,
)
def upload_process_event_log(
    process_id: str,
    response: Response,
    file: UploadFile = File(...),
    delimiter: Delimiter | None = Form(None),
) -> UploadedEventLogResponse:
    """Carica un CSV o XES: lo conserva e restituisce colonne, separatore e prime righe."""
    payload = file.file.read(MAX_FILE_BYTES + 1)
    try:
        uploaded = upload_event_log(process_id, clean_filename(file.filename), payload, delimiter)
    except EventLogTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except EventLogFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    if uploaded is None:
        raise HTTPException(status_code=404, detail=_PROCESS_NOT_FOUND)
    if not uploaded.created:
        response.status_code = 200
    return uploaded


@router.get("/processes/{process_id}/event-logs")
def list_process_event_logs(process_id: str) -> list[EventLogResponse]:
    logs = storage.list_event_logs(process_id)
    if logs is None:
        raise HTTPException(status_code=404, detail=_PROCESS_NOT_FOUND)
    return logs


@router.get("/event-logs/{event_log_id}")
def get_event_log(event_log_id: str) -> EventLogResponse:
    log = storage.get_event_log(event_log_id)
    if log is None:
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND)
    return log


@router.get("/event-logs/{event_log_id}/preview")
def get_event_log_preview(
    event_log_id: str, delimiter: Delimiter | None = Query(None)
) -> EventLogPreviewResponse:
    """Le prime righe del file, con il separatore in uso o con quello indicato."""
    try:
        return preview_event_log(event_log_id, delimiter)
    except EventLogNotFound as exc:
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND) from exc
    except EventLogFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/event-logs/{event_log_id}/mapping")
def apply_event_log_mapping(
    event_log_id: str, request: ApplyEventLogMappingRequest
) -> EventLogAnalysisResponse:
    """Applica il mapping: report di qualita', abbinamento al BPMN e KPI, salvati sul log."""
    try:
        return apply_mapping(event_log_id, request)
    except EventLogNotFound as exc:
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND) from exc
    except TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=_TEMPLATE_NOT_FOUND) from exc
    except EventLogFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/event-logs/{event_log_id}/analysis")
def get_event_log_analysis(event_log_id: str) -> EventLogAnalysisResponse:
    analysis = storage.get_analysis(event_log_id)
    if analysis is not None:
        return analysis
    if storage.get_event_log(event_log_id) is None:
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND)
    raise HTTPException(status_code=409, detail="Il log non è ancora stato mappato.")


@router.delete("/event-logs/{event_log_id}", status_code=204)
def delete_event_log(event_log_id: str) -> Response:
    if not storage.delete_event_log(event_log_id):
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND)
    return Response(status_code=204)


@router.get("/event-log-templates")
def list_event_log_templates() -> list[EventLogTemplateResponse]:
    """L'ultima versione di ogni template del tenant."""
    return storage.list_templates()


@router.post("/event-log-templates", status_code=201)
def save_event_log_template(request: SaveEventLogTemplateRequest) -> EventLogTemplateResponse:
    """Salva un mapping; con ``template_key`` ne aggiunge una versione."""
    saved = storage.save_template(
        name=request.name,
        mapping=request.mapping,
        columns=request.columns,
        template_key=request.template_key,
    )
    if saved is None:
        raise HTTPException(status_code=404, detail=_TEMPLATE_NOT_FOUND)
    return saved


@router.get("/event-log-templates/{template_key}/versions")
def list_event_log_template_versions(template_key: str) -> list[EventLogTemplateResponse]:
    versions = storage.template_versions(template_key)
    if not versions:
        raise HTTPException(status_code=404, detail=_TEMPLATE_NOT_FOUND)
    return versions
