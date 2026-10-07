"""Il mapping completo: da una tabella qualsiasi all'event log canonico.

Il consulente dice che cosa significa ogni colonna (``ColumnMapping``); qui si
applica, riga per riga, e si registra tutto cio' che non torna nel report di
qualita'. Nessuna riga sparisce in silenzio: ogni esclusione ha un codice, un
conteggio e le prime righe del file in cui succede.

Due forme di timestamp:
- ``start`` + ``end``: una riga per esecuzione, con inizio e fine;
- ``timestamp`` + ``lifecycle``: una riga per transizione (start/complete), come
  in XES; le coppie si ricompongono per caso e attivita', in ordine.
Con solo ``end`` (o solo transizioni complete) l'inizio resta ignoto.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.eventlog.model import AttributeValue, CanonicalEvent, EventLog
from backend.eventlog.readers import Table

AttributeType = Literal["number", "text", "category", "date"]
_START_WORDS = {"start", "begin", "started", "inizio", "avvio"}
_COMPLETE_WORDS = {"complete", "completed", "end", "fine", "completato"}
_SAMPLE_ROWS = 5


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributeColumn(_Spec):
    column: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    type: AttributeType = "text"


class TimestampFormat(_Spec):
    """``pattern`` alla strftime (es. ``%d/%m/%Y %H:%M``); vuoto = ISO 8601.

    I timestamp senza fuso si leggono in ``timezone``; quelli con il fuso lo tengono.
    """

    pattern: str | None = None
    timezone: str = "Europe/Rome"

    @model_validator(mode="after")
    def _known_zone(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuso orario sconosciuto: {self.timezone}") from exc
        return self


class NumberFormat(_Spec):
    decimal: Literal[".", ","] = "."
    thousands: Literal["", ".", ",", " ", "'"] = ""

    @model_validator(mode="after")
    def _distinct(self):
        if self.decimal == self.thousands:
            raise ValueError("separatore decimale e delle migliaia devono essere diversi")
        return self


class ColumnMapping(_Spec):
    """Che cosa significa ogni colonna della tabella."""

    case_id: tuple[str, ...] = Field(min_length=1)
    activity: tuple[str, ...] = Field(min_length=1)
    start: str | None = None
    end: str | None = None
    timestamp: str | None = None
    lifecycle: str | None = None
    resource: str | None = None
    role: str | None = None
    cost: str | None = None
    case_attributes: tuple[AttributeColumn, ...] = ()
    event_attributes: tuple[AttributeColumn, ...] = ()
    timestamps: TimestampFormat = TimestampFormat()
    numbers: NumberFormat = NumberFormat()
    # Separatore quando caso o attivita' vengono da piu' colonne.
    joiner: str = Field(default=" · ", max_length=5)

    @model_validator(mode="after")
    def _one_time_shape(self):
        by_interval = self.end is not None
        by_transition = self.timestamp is not None
        if by_interval == by_transition:
            raise ValueError("indica o la colonna di fine (con inizio facoltativo) o timestamp e ciclo di vita")
        if by_interval and self.lifecycle:
            raise ValueError("il ciclo di vita si usa con la colonna timestamp, non con inizio e fine")
        if by_transition and self.start:
            raise ValueError("con timestamp e ciclo di vita non serve la colonna di inizio")
        names = [a.name for a in self.case_attributes + self.event_attributes]
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"attributi con lo stesso nome: {', '.join(duplicated)}")
        return self

    def columns(self) -> set[str]:
        used = {*self.case_id, *self.activity}
        used |= {c for c in (self.start, self.end, self.timestamp, self.lifecycle, self.resource, self.role, self.cost) if c}
        used |= {a.column for a in self.case_attributes + self.event_attributes}
        return used


# --------------------------------------------------------------------------- #
# Report di qualita'
# --------------------------------------------------------------------------- #

IssueCode = Literal[
    "missing_case_id",
    "missing_activity",
    "missing_timestamp",
    "unreadable_timestamp",
    "end_before_start",
    "duplicate_event",
    "unpaired_start",
    "unknown_lifecycle",
    "unreadable_number",
    "unreadable_date",
    "case_attribute_conflict",
]

_MESSAGES: dict[IssueCode, str] = {
    "missing_case_id": "Righe senza identificativo del caso: escluse.",
    "missing_activity": "Righe senza attività: escluse.",
    "missing_timestamp": "Righe senza timestamp di fine: escluse.",
    "unreadable_timestamp": "Timestamp non leggibili con il formato indicato: righe escluse.",
    "end_before_start": "Fine precedente all'inizio: righe escluse.",
    "duplicate_event": "Eventi identici ripetuti: tenuto uno solo.",
    "unpaired_start": "Inizi senza completamento: esecuzioni non concluse, escluse.",
    "unknown_lifecycle": "Valori del ciclo di vita diversi da inizio/completamento: righe escluse.",
    "unreadable_number": "Numeri non leggibili: valore lasciato vuoto.",
    "unreadable_date": "Date negli attributi non leggibili: valore lasciato vuoto.",
    "case_attribute_conflict": "Attributo del caso con valori diversi nello stesso caso: tenuto il primo.",
}
_EXCLUDING: set[IssueCode] = {
    "missing_case_id", "missing_activity", "missing_timestamp", "unreadable_timestamp",
    "end_before_start", "unpaired_start", "unknown_lifecycle",
}


@dataclass(slots=True)
class Issue:
    code: IssueCode
    message: str
    count: int = 0
    rows: list[int] = field(default_factory=list)
    excludes_rows: bool = False


@dataclass(slots=True)
class QualityReport:
    rows_read: int
    events: int
    cases: int
    activities: int
    resources: int
    period_start: datetime | None
    period_end: datetime | None
    events_without_start: int
    issues: list[Issue]

    @property
    def rows_excluded(self) -> int:
        return sum(issue.count for issue in self.issues if issue.excludes_rows)


class _Issues:
    def __init__(self) -> None:
        self._by_code: dict[IssueCode, Issue] = {}

    def add(self, code: IssueCode, row: int) -> None:
        issue = self._by_code.setdefault(
            code, Issue(code=code, message=_MESSAGES[code], excludes_rows=code in _EXCLUDING)
        )
        issue.count += 1
        if len(issue.rows) < _SAMPLE_ROWS:
            issue.rows.append(row)

    def all(self) -> list[Issue]:
        return sorted(self._by_code.values(), key=lambda issue: (-issue.count, issue.code))


# --------------------------------------------------------------------------- #
# Applicazione del mapping
# --------------------------------------------------------------------------- #


class MappingError(ValueError):
    """Il mapping non si applica a questa tabella (colonne assenti)."""


def apply_mapping(
    table: Table,
    mapping: ColumnMapping,
    *,
    source_name: str | None = None,
) -> tuple[EventLog, QualityReport]:
    missing = sorted(mapping.columns() - set(table.header))
    if missing:
        raise MappingError(f"Colonne non presenti nel file: {', '.join(missing)}.")
    index = {name: position for position, name in enumerate(table.header)}
    zone = ZoneInfo(mapping.timestamps.timezone)
    issues = _Issues()

    def cell(row: tuple[str, ...], column: str | None) -> str:
        return row[index[column]].strip() if column else ""

    def joined(row: tuple[str, ...], columns: tuple[str, ...]) -> str:
        parts = [cell(row, column) for column in columns]
        return mapping.joiner.join(parts) if all(parts) else ""

    raw: list[tuple[int, CanonicalEvent, str | None]] = []  # (riga, evento, transizione)
    case_attributes: dict[str, dict[str, AttributeValue]] = defaultdict(dict)

    for position, row in enumerate(table.rows):
        line = position + 2  # 1 = intestazione
        case_id = joined(row, mapping.case_id)
        activity = joined(row, mapping.activity)
        if not case_id:
            issues.add("missing_case_id", line)
            continue
        if not activity:
            issues.add("missing_activity", line)
            continue

        time_column = mapping.end or mapping.timestamp
        raw_time = cell(row, time_column)
        if not raw_time:
            issues.add("missing_timestamp", line)
            continue
        when = _parse_time(raw_time, mapping.timestamps.pattern, zone)
        if when is None:
            issues.add("unreadable_timestamp", line)
            continue
        start = None
        if mapping.start and cell(row, mapping.start):
            start = _parse_time(cell(row, mapping.start), mapping.timestamps.pattern, zone)
            if start is None:
                issues.add("unreadable_timestamp", line)
                continue
            if start > when:
                issues.add("end_before_start", line)
                continue

        transition: str | None = None
        if mapping.lifecycle:
            value = cell(row, mapping.lifecycle).lower()
            if value in _START_WORDS:
                transition = "start"
            elif value in _COMPLETE_WORDS or value == "":
                transition = "complete"
            else:
                issues.add("unknown_lifecycle", line)
                continue

        cost = None
        if mapping.cost and cell(row, mapping.cost):
            cost = _parse_number(cell(row, mapping.cost), mapping.numbers)
            if cost is None:
                issues.add("unreadable_number", line)

        attributes = _attributes(row, mapping.event_attributes, cell, mapping, zone, issues, line)
        for name, value in _attributes(row, mapping.case_attributes, cell, mapping, zone, issues, line).items():
            known = case_attributes[case_id]
            if name in known and known[name] != value:
                issues.add("case_attribute_conflict", line)
            else:
                known.setdefault(name, value)

        raw.append((
            line,
            CanonicalEvent(
                case_id=case_id,
                activity=activity,
                end=when,
                start=start,
                resource=cell(row, mapping.resource) or None,
                role=cell(row, mapping.role) or None,
                cost=cost,
                attributes=attributes,
                source_row=line,
            ),
            transition,
        ))

    events = _pair_transitions(raw, issues) if mapping.lifecycle else [event for _, event, _ in raw]
    events = _deduplicate(events, issues)
    log = EventLog(
        origin="real",
        events=tuple(events),
        case_attributes={case: dict(values) for case, values in case_attributes.items() if case in {e.case_id for e in events}},
        source_name=source_name,
    )
    return log, _report(table, log, issues)


def _pair_transitions(raw: list[tuple[int, CanonicalEvent, str | None]], issues: _Issues) -> list[CanonicalEvent]:
    """Ricompone start/complete per caso e attivita', nell'ordine del tempo."""
    open_starts: dict[tuple[str, str], list[tuple[int, CanonicalEvent]]] = defaultdict(list)
    events: list[CanonicalEvent] = []
    for line, event, transition in sorted(raw, key=lambda item: (item[1].end, item[0])):
        key = (event.case_id, event.activity)
        if transition == "start":
            open_starts[key].append((line, event))
            continue
        if open_starts[key]:
            _, started = open_starts[key].pop(0)
            events.append(_with_start(event, started.end, merge=started))
        else:
            events.append(event)
    for pending in open_starts.values():
        for line, _ in pending:
            issues.add("unpaired_start", line)
    return events


def _with_start(event: CanonicalEvent, start: datetime, *, merge: CanonicalEvent) -> CanonicalEvent:
    return CanonicalEvent(
        case_id=event.case_id,
        activity=event.activity,
        end=event.end,
        start=start,
        resource=event.resource or merge.resource,
        role=event.role or merge.role,
        cost=event.cost if event.cost is not None else merge.cost,
        attributes={**merge.attributes, **event.attributes},
        source_row=event.source_row,
    )


def _deduplicate(events: list[CanonicalEvent], issues: _Issues) -> list[CanonicalEvent]:
    seen: set[tuple] = set()
    kept: list[CanonicalEvent] = []
    for event in events:
        key = (event.case_id, event.activity, event.start, event.end, event.resource)
        if key in seen:
            issues.add("duplicate_event", event.source_row or 0)
            continue
        seen.add(key)
        kept.append(event)
    return kept


def _attributes(row, columns, cell, mapping: ColumnMapping, zone: ZoneInfo, issues: _Issues, line: int) -> dict[str, AttributeValue]:
    values: dict[str, AttributeValue] = {}
    for attribute in columns:
        raw = cell(row, attribute.column)
        if not raw:
            continue
        if attribute.type == "number":
            number = _parse_number(raw, mapping.numbers)
            if number is None:
                issues.add("unreadable_number", line)
                continue
            values[attribute.name] = number
        elif attribute.type == "date":
            moment = _parse_time(raw, mapping.timestamps.pattern, zone)
            if moment is None:
                issues.add("unreadable_date", line)
                continue
            values[attribute.name] = moment
        else:
            values[attribute.name] = raw
    return values


def _parse_time(raw: str, pattern: str | None, zone: ZoneInfo) -> datetime | None:
    try:
        moment = datetime.strptime(raw, pattern) if pattern else datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=zone)


_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _parse_number(raw: str, numbers: NumberFormat) -> float | None:
    text = raw.replace(" ", " ").strip()
    if numbers.thousands:
        text = text.replace(numbers.thousands, "")
    if numbers.decimal == ",":
        text = text.replace(",", ".")
    text = text.replace(" ", "")
    return float(text) if _NUMBER.match(text) else None


def _report(table: Table, log: EventLog, issues: _Issues) -> QualityReport:
    starts = [event.start for event in log.events if event.start]
    ends = [event.end for event in log.events]
    return QualityReport(
        rows_read=len(table.rows),
        events=len(log.events),
        cases=len({event.case_id for event in log.events}),
        activities=len(log.activities()),
        resources=len(log.resources()),
        period_start=min(starts + ends) if ends else None,
        period_end=max(ends) if ends else None,
        events_without_start=sum(1 for event in log.events if event.start is None),
        issues=issues.all(),
    )
