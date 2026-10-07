"""Contratto HTTP dell'import degli event log (SIM-15).

Il mapping viaggia con lo stesso modello che lo applica (``ColumnMapping``):
una sola definizione, validata al confine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.eventlog.bpmn_match import MatchReason
from backend.eventlog.mapping import ColumnMapping, IssueCode

EventLogStatus = Literal["uploaded", "mapped"]
EventLogFormat = Literal["csv", "xes"]
# Gli stessi di `readers.CANDIDATE_DELIMITERS`.
Delimiter = Literal[",", ";", "\t", "|"]


class EventLogTemplateRef(BaseModel):
    id: int
    template_key: str
    version: int
    name: str


class EventLogResponse(BaseModel):
    id: str
    process_id: str
    name: str
    format: EventLogFormat
    delimiter: str | None
    byte_size: int
    row_count: int
    columns: list[str]
    status: EventLogStatus
    mapping: ColumnMapping | None
    template: EventLogTemplateRef | None
    created_at: str
    mapped_at: str | None


class EventLogPreviewResponse(BaseModel):
    format: EventLogFormat
    delimiter: str | None
    columns: list[str]
    row_count: int
    sample_rows: list[list[str]]


class UploadedEventLogResponse(EventLogResponse):
    created: bool
    preview: EventLogPreviewResponse


class ApplyEventLogMappingRequest(BaseModel):
    """Il mapping scritto nel wizard, oppure la versione di un template salvato."""

    model_config = ConfigDict(extra="forbid")

    mapping: ColumnMapping | None = None
    template_id: int | None = None
    # Il separatore indicato dal consulente al posto di quello riconosciuto.
    delimiter: Delimiter | None = None
    # Attivita' del log -> elemento BPMN (None = ignorata). Assente: il
    # suggerimento automatico per nomi identici.
    activity_matches: dict[str, str | None] | None = None
    # Risorsa del log -> risorsa del modello (None = ignorata). Assente: solo
    # nomi identici.
    resource_matches: dict[str, str | None] | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if (self.mapping is None) == (self.template_id is None):
            raise ValueError("indica il mapping oppure il template da applicare, non entrambi")
        return self


class QualityIssueResponse(BaseModel):
    code: IssueCode
    message: str
    count: int
    rows: list[int]
    excludes_rows: bool


class QualityReportResponse(BaseModel):
    rows_read: int
    rows_excluded: int
    events: int
    cases: int
    activities: int
    resources: int
    period_start: datetime | None
    period_end: datetime | None
    events_without_start: int
    issues: list[QualityIssueResponse]


class ActivityMatchResponse(BaseModel):
    activity: str
    events: int
    element_id: str | None
    reason: MatchReason


class ModelElementResponse(BaseModel):
    element_id: str
    name: str


class ActivityMatchReportResponse(BaseModel):
    # La versione del BPMN usata; None se il processo non ha ancora un BPMN.
    bpmn_version_id: int | None
    # True se l'abbinamento e' quello deciso dal consulente.
    confirmed: bool
    matches: list[ActivityMatchResponse]
    unmatched_activities: list[str]
    unobserved_elements: list[ModelElementResponse]


class ResourceMatchResponse(BaseModel):
    resource: str
    events: int
    model_resource_id: str | None
    reason: MatchReason


class ModelResourceResponse(BaseModel):
    resource_id: str
    name: str


class ResourceMatchReportResponse(BaseModel):
    """Le risorse del log (persone, utenti) e le risorse del modello (pool e lane)."""

    confirmed: bool
    matches: list[ResourceMatchResponse]
    unmatched_resources: list[str]
    unobserved_model_resources: list[ModelResourceResponse]
    # Eventi senza risorsa nel log: non si abbinano a niente, si contano.
    events_without_resource: int


class EventLogAnalysisResponse(BaseModel):
    event_log: EventLogResponse
    quality: QualityReportResponse
    activities: ActivityMatchReportResponse
    resources: ResourceMatchReportResponse
    # Gli stessi KPI di un run simulato; None se nessun evento e' valido.
    summary: dict[str, Any] | None


class SaveEventLogTemplateRequest(BaseModel):
    """Salva un mapping. Con ``template_key`` aggiunge una versione a un template esistente."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    mapping: ColumnMapping
    columns: list[str] = Field(min_length=1, max_length=500)
    template_key: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _mapping_uses_these_columns(self):
        missing = sorted(self.mapping.columns() - set(self.columns))
        if missing:
            raise ValueError(f"il mapping usa colonne che il template non ha: {', '.join(missing)}")
        return self


class EventLogTemplateResponse(BaseModel):
    id: int
    template_key: str
    version: int
    name: str
    mapping: ColumnMapping
    columns: list[str]
    created_at: str
