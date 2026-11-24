"""Import degli event log reali sui processi (SIM-15) e template di mapping."""

from dataclasses import replace

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from backend.eventlog import storage
from backend.eventlog.mapping import MappingError, apply_mapping as read_mapped_events
from backend.eventlog.model import EventLog
from backend.eventlog.readers import EventLogFileError, read_table
from backend.eventlog.synthetic import from_log_events
from backend.eventlog.validation import validate
from backend.simulation.horizon import horizon_end, within_horizon
from backend.simulation.log_processor import after_warmup, parse_prosimos_log
from backend.simulation.storage import get_simulation_log_csv, get_simulation_run
from backend.eventlog.service import (
    EventLogNotFound,
    EventLogTooLarge,
    TemplateNotFound,
    apply_mapping,
    clean_filename,
    conformance,
    preview_event_log,
    upload_event_log,
)
from backend.schemas.eventlog import (
    ApplyEventLogMappingRequest,
    Delimiter,
    EventLogAnalysisResponse,
    EventLogConformanceResponse,
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


@router.get("/event-logs/{event_log_id}/validation")
def validate_event_log(event_log_id: str, run_ids: list[int] = Query(...)) -> dict:
    """KPI confrontabili e distanze, una osservazione per replica completata."""
    if not 1 <= len(run_ids) <= 20 or len(set(run_ids)) != len(run_ids):
        raise HTTPException(status_code=422, detail="Seleziona da 1 a 20 repliche distinte.")
    analysis = storage.get_analysis(event_log_id)
    loaded = storage.load_event_log_file(event_log_id)
    if analysis is None or loaded is None or analysis.event_log.mapping is None:
        raise HTTPException(status_code=404, detail="Event log mappato non trovato.")
    source, payload = loaded
    table = read_table(source.name, payload, source.delimiter)
    real, _ = read_mapped_events(table, analysis.event_log.mapping, source_name=source.name)
    real_labels = {item.activity: item.element_id for item in analysis.activities.matches if item.element_id}
    real = EventLog(origin="real", events=tuple(replace(event, activity=real_labels.get(event.activity, event.activity))
                                              for event in real.events), source_name=real.source_name)
    simulated = []
    provenance = []
    group = None
    scenario = None
    fingerprint = None
    for position, run_id in enumerate(run_ids):
        run = get_simulation_run(run_id)
        if run is None or run["process_id"] != source.process_id or run["status"] != "completed":
            raise HTTPException(status_code=422, detail=f"La replica #{run_id} non appartiene al processo o non è completa.")
        request = run.get("request") or {}
        if len(run_ids) > 1:
            current_group = request.get("replication_group")
            current_scenario = request.get("workspace_scenario")
            current_fingerprint = request.get("bpmn_fingerprint")
            if not current_group or (position > 0 and (group != current_group or scenario != current_scenario or fingerprint != current_fingerprint)):
                raise HTTPException(status_code=422, detail="Le repliche devono appartenere allo stesso gruppo e alla stessa revisione.")
            group, scenario, fingerprint = current_group, current_scenario, current_fingerprint
        csv_text = get_simulation_log_csv(run_id)
        if not csv_text:
            raise HTTPException(status_code=422, detail=f"Il log della replica #{run_id} non è disponibile.")
        events = parse_prosimos_log(csv_text)
        if request.get("horizon_days") and request.get("start_date"):
            end = horizon_end(request["start_date"], int(request["horizon_days"]))
            events, _, _ = within_horizon(events, end, int(request["horizon_days"]))
        events = after_warmup(events, int(request.get("warmup_cases") or 0))
        generated = from_log_events(events)
        labels = {row["name"]: row["el"] for row in (run.get("summary") or {}).get("byActivity", [])
                  if isinstance(row.get("name"), str) and isinstance(row.get("el"), str)}
        generated = EventLog(origin="simulated", events=tuple(replace(event, activity=labels.get(event.activity, event.activity))
                                                        for event in generated.events))
        simulated.append((run_id, generated))
        provenance.append({"runId": run_id, "seed": (run.get("result") or {}).get("Seed"),
                           "engine": run.get("engine"), "engineVersion": (run.get("result") or {}).get("EngineVersion"),
                           "scenario": request.get("workspace_scenario"), "bpmnFingerprint": request.get("bpmn_fingerprint"),
                           "startDate": request.get("start_date"),
                           "warmupCases": request.get("warmup_cases") or 0})
    try:
        result = validate(real, simulated)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["quality"] = {"rowsExcluded": analysis.quality.rows_excluded,
                         "eventsWithoutStart": analysis.quality.events_without_start}
    result["initialActivities"] = sorted({events[0].activity for events in real.cases().values() if events})
    result["provenance"] = {"eventLogId": event_log_id, "runs": provenance}
    return result


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
    event_log_id: str,
    delimiter: Delimiter | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> EventLogPreviewResponse:
    """Una pagina del file, con il separatore rilevato o quello indicato."""
    try:
        return preview_event_log(event_log_id, delimiter, offset=offset, limit=limit)
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


@router.get("/event-logs/{event_log_id}/conformance")
def get_event_log_conformance(event_log_id: str) -> EventLogConformanceResponse:
    """I casi reali riprodotti sul BPMN: quanti lo seguono e dove ne escono.

    ``ConformanceUnavailable`` diventa un 409 con codice stabile nel gestore
    comune (``backend/api/errors.py``).
    """
    try:
        return conformance(event_log_id)
    except EventLogNotFound as exc:
        raise HTTPException(status_code=404, detail=_LOG_NOT_FOUND) from exc
    except EventLogFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
