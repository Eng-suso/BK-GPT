"""L'import di un event log su un processo, dall'upload ai KPI.

Tiene insieme lettura del file (``readers``), analisi (``analysis``),
persistenza (``storage``) e il BPMN corrente del processo. Le route lo
chiamano e traducono le eccezioni in codici HTTP; qui non c'e' HTTP.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from backend.eventlog import storage
from backend.eventlog.analysis import Preview, analyze, preview
from backend.eventlog.bpmn_match import ModelElement
from backend.eventlog.conformance import ConformanceModelError, check_conformance
from backend.eventlog.kpi import summarize
from backend.eventlog.mapping import apply_mapping as map_table
from backend.eventlog.periods import cases_started
from backend.eventlog.readers import EventLogFileError, Table, read_table
from backend.schemas.eventlog import (
    ActivityMatchReportResponse,
    ApplyEventLogMappingRequest,
    ConformanceDeviationResponse,
    ConformanceWarningResponse,
    ConformanceVariantResponse,
    EventLogAnalysisResponse,
    EventLogConformanceResponse,
    EventLogPreviewResponse,
    EventLogResponse,
    QualityReportResponse,
    ResourceMatchReportResponse,
    UploadedEventLogResponse,
)
from backend.simulation.engine import get_engine
from backend.simulation.scenario_builder import describe_scenario_template
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
        delimiter_chosen=delimiter is not None,
    ))
    if stored is None:
        return None
    log, created = stored
    return UploadedEventLogResponse(**log.model_dump(), created=created, preview=_preview_response(preview(table)))


def preview_event_log(event_log_id: str, delimiter: str | None = None, *, offset: int = 0, limit: int = 20) -> EventLogPreviewResponse:
    """L'anteprima del file con un altro separatore, senza cambiare nulla."""
    _log, table = _read(event_log_id, delimiter)
    return _preview_response(preview(table, rows=limit, offset=offset))


def apply_mapping(event_log_id: str, request: ApplyEventLogMappingRequest) -> EventLogAnalysisResponse:
    """Applica il mapping (o il template) al file e salva qualita', abbinamento e KPI.

    Raises:
        EventLogNotFound, TemplateNotFound: non esistono nel tenant.
        MappingError: il mapping cita colonne che il file non ha.
        ValueError: l'abbinamento cita elementi o risorse che il modello non ha.
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

    model = _model_targets(log.process_id)
    bpmn_version_id = model.bpmn_version_id
    result = analyze(
        table,
        mapping,
        model.activities,
        resources=model.resources,
        confirmed_matches=request.activity_matches,
        confirmed_resource_matches=request.resource_matches,
        source_name=log.name,
    )
    quality = result.quality
    saved = storage.save_analysis(event_log_id, storage.AnalysisRecord(
        delimiter=table.delimiter,
        mapping=mapping,
        template_id=template_id,
        activity_matches=request.activity_matches,
        resource_matches=request.resource_matches,
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
        resources=ResourceMatchReportResponse(
            confirmed=request.resource_matches is not None,
            matches=[
                {"resource": m.activity, "events": m.events, "model_resource_id": m.element_id, "reason": m.reason}
                for m in result.resource_matches.matches
            ],
            unmatched_resources=list(result.resource_matches.unmatched_activities),
            unobserved_model_resources=[
                {"resource_id": r.element_id, "name": r.name} for r in result.resource_matches.unobserved_elements
            ],
            events_without_resource=result.events_without_resource,
        ),
        summary=result.summary,
    ))
    if saved is None:
        # Cancellato fra la lettura e la scrittura.
        raise EventLogNotFound(event_log_id)
    return saved


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    """SIM-28: i KPI dei casi di un log iniziati in un periodo."""

    event_log: EventLogResponse
    cases: int
    summary: dict | None


def period_summary(event_log_id: str, *, since: date | None = None, before: date | None = None) -> PeriodSummary:
    """I KPI dei soli casi iniziati in [``since``, ``before``), con il mapping salvato del log.

    Raises:
        EventLogNotFound: il log non esiste nel tenant.
        ValueError: il log non e' ancora mappato.
    """
    log, table = _read(event_log_id, None)
    if log.mapping is None:
        raise ValueError(f"Il log «{log.name}» non è ancora mappato: completa il mapping nel wizard.")
    canonical, _ = map_table(table, log.mapping, source_name=log.name)
    period = cases_started(canonical, since=since, before=before)
    cases = len({event.case_id for event in period.events})
    return PeriodSummary(event_log=log, cases=cases, summary=summarize(period) if period.events else None)


class ConformanceUnavailable(ValueError):
    """Mancano il mapping o il modello: la conformance non si puo' calcolare.

    ``code`` e' stabile (``not_mapped``, ``no_model``, ``model_not_replayable``):
    il client lo traduce, il messaggio resta per i log e per le API.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


#: Le varianti restituite nella risposta: le piu' frequenti. Il calcolo le usa tutte.
CONFORMANCE_VARIANTS_IN_RESPONSE = 50


def conformance(event_log_id: str) -> EventLogConformanceResponse:
    """I casi reali del log riprodotti sul BPMN corrente del processo.

    Usa il mapping delle colonne e l'abbinamento attivita'-elementi salvati
    dall'ultimo ``apply_mapping``: e' il consulente che ha deciso quale
    attivita' del log e' quale elemento del modello, e il replay non lo
    ridecide.

    Raises:
        EventLogNotFound: il log non esiste nel tenant.
        ConformanceUnavailable: log non mappato, processo senza BPMN, o BPMN
            che non si puo' riprodurre.
    """
    # I controlli economici prima di leggere e analizzare il file.
    log = storage.get_event_log(event_log_id)
    if log is None:
        raise EventLogNotFound(event_log_id)
    analysis = storage.get_analysis(event_log_id)
    if log.mapping is None or analysis is None:
        raise ConformanceUnavailable(
            "not_mapped", f"Il log «{log.name}» non è ancora mappato: completa il mapping nel wizard."
        )
    process = get_process(log.process_id)
    model = get_bpmn_model(process["bpmn_model_id"]) if process else None
    xml = (model or {}).get("xml") or ""
    if not xml.strip():
        raise ConformanceUnavailable("no_model", "Il processo non ha ancora un BPMN da confrontare con il log.")

    log, table = _read(event_log_id, None)

    assert log.mapping is not None  # controllato sopra, sulla stessa riga
    canonical, _ = map_table(table, log.mapping, source_name=log.name)
    matches = {m.activity: m.element_id for m in analysis.activities.matches}
    try:
        # Gli element_id dell'abbinamento vengono dal BPMN normalizzato per il
        # motore (``_model_targets``): si riproduce lo stesso.
        result = check_conformance(canonical, get_engine().prepare_bpmn(xml), matches)
    except ConformanceModelError as exc:
        raise ConformanceUnavailable("model_not_replayable", str(exc)) from exc

    # Un BPMN cambiato dopo l'abbinamento si legge dalle due versioni nella risposta.
    bpmn_version_id = (model or {}).get("version_id")
    names = {m.element_id: m.name for m in analysis.activities.unobserved_elements}
    names.update({d.element_id: d.name for d in result.deviations})
    return EventLogConformanceResponse(
        event_log=log,
        bpmn_version_id=bpmn_version_id,
        mapping_bpmn_version_id=analysis.activities.bpmn_version_id,
        fitness=result.fitness,
        cases=result.cases,
        fitting_cases=result.fitting_cases,
        fitting_share=result.fitting_share,
        deviations=[
            ConformanceDeviationResponse(
                element_id=d.element_id,
                name=d.name,
                executed_out_of_order=d.executed_out_of_order,
                left_waiting=d.left_waiting,
                cases_affected=d.cases_affected,
            )
            for d in result.deviations
        ],
        variants=[
            ConformanceVariantResponse(
                activities=list(v.activities),
                cases=v.cases,
                fitness=v.fitness,
                fits=v.fits,
                out_of_order=list(v.out_of_order),
                waiting=list(v.waiting),
                unmodeled=list(v.unmodeled),
            )
            for v in result.variants[:CONFORMANCE_VARIANTS_IN_RESPONSE]
        ],
        unmodeled_activities=result.unmodeled_activities,
        unobserved_elements=[
            {"element_id": element, "name": names.get(element, element)}
            for element in result.unobserved_elements
        ],
        excluded_variants=result.excluded_variants,
        excluded_cases=result.excluded_cases,
        warnings=[ConformanceWarningResponse(code=w.code, params=dict(w.params)) for w in result.warnings],
    )


def _read(event_log_id: str, delimiter: str | None) -> tuple[EventLogResponse, Table]:
    loaded = storage.load_event_log_file(event_log_id)
    if loaded is None:
        raise EventLogNotFound(event_log_id)
    log, payload = loaded
    if delimiter is not None and log.format == "xes":
        raise EventLogFileError("Un file XES non ha separatore.")
    return log, read_table(log.name, payload, delimiter or log.delimiter)


@dataclass(frozen=True, slots=True)
class _ModelTargets:
    activities: list[ModelElement]
    resources: list[ModelElement]
    bpmn_version_id: int | None


def _model_targets(process_id: str) -> _ModelTargets:
    """Attivita' e risorse del modello corrente del processo, e la versione da cui vengono.

    Le stesse che vede la configurazione della simulazione
    (``describe_scenario_template`` sul BPMN normalizzato): un'attivita' del log
    si abbina a un elemento che il motore simula davvero.
    """
    process = get_process(process_id)
    model = get_bpmn_model(process["bpmn_model_id"]) if process else None
    if model is None or not (model.get("xml") or "").strip():
        return _ModelTargets([], [], None)
    xml = model["xml"]
    template = describe_scenario_template(get_engine().prepare_bpmn(xml), source_bpmn_xml=xml)
    return _ModelTargets(
        activities=[ModelElement(task.element_id, task.name) for task in template.tasks],
        resources=[ModelElement(resource.id, resource.name) for resource in template.resources],
        bpmn_version_id=model.get("version_id"),
    )


def _preview_response(value: Preview) -> EventLogPreviewResponse:
    return EventLogPreviewResponse(
        format=value.format,
        delimiter=value.delimiter,
        columns=list(value.columns),
        row_count=value.row_count,
        sample_rows=[list(row) for row in value.sample_rows],
    )
