"""Un file di event log, letto e mappato: anteprima, qualita', abbinamento e KPI.

E' il passaggio che fanno le API di import, tenuto qui senza database ne' HTTP:
le stesse funzioni di ``readers``, ``mapping``, ``bpmn_match`` e ``kpi``, in
ordine. Un log senza eventi validi non ha KPI (``summary`` assente), non KPI a
zero: il report di qualita' dice perche'.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.eventlog.bpmn_match import MatchReport, ModelElement, apply_confirmed, suggest_matches
from backend.eventlog.kpi import summarize
from backend.eventlog.mapping import ColumnMapping, QualityReport, apply_mapping
from backend.eventlog.model import EventLog
from backend.eventlog.readers import Table

PREVIEW_ROWS = 20


@dataclass(frozen=True, slots=True)
class Preview:
    format: str
    delimiter: str | None
    columns: tuple[str, ...]
    row_count: int
    sample_rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class Analysis:
    log: EventLog
    quality: QualityReport
    matches: MatchReport
    # Le stesse regole dell'abbinamento delle attivita', sulle risorse: nomi
    # identici in automatico, il resto lo decide il consulente.
    resource_matches: MatchReport
    events_without_resource: int
    # I KPI con lo stesso calcolo dei run simulati; None se nessun evento e' valido.
    summary: dict[str, Any] | None


def preview(table: Table, rows: int = PREVIEW_ROWS) -> Preview:
    return Preview(
        format=table.format,
        delimiter=table.delimiter,
        columns=table.header,
        row_count=len(table.rows),
        sample_rows=table.rows[:rows],
    )


def analyze(
    table: Table,
    mapping: ColumnMapping,
    elements: list[ModelElement],
    *,
    resources: list[ModelElement] | None = None,
    confirmed_matches: dict[str, str | None] | None = None,
    confirmed_resource_matches: dict[str, str | None] | None = None,
    source_name: str | None = None,
) -> Analysis:
    """Applica il mapping e abbina attivita' e risorse del log al modello.

    Con ``confirmed_matches`` vale la decisione del consulente (attivita' ->
    elemento, ``None`` per ignorarla); senza, il suggerimento per nomi identici.
    ``confirmed_resource_matches`` fa lo stesso per le risorse (persona o utente
    del log -> pool o lane del modello). I KPI per elemento usano l'abbinamento
    delle attivita' risultante.

    Raises:
        MappingError: il mapping cita colonne che il file non ha.
        ValueError: l'abbinamento cita elementi o risorse che il modello non ha.
    """
    log, quality = apply_mapping(table, mapping, source_name=source_name)
    matches = _match(Counter(event.activity for event in log.events), elements, confirmed_matches)
    resource_matches = _match(
        Counter(event.resource for event in log.events if event.resource),
        resources or [],
        confirmed_resource_matches,
    )
    summary = summarize(log, matches.mapping()) if log.events else None
    return Analysis(
        log=log,
        quality=quality,
        matches=matches,
        resource_matches=resource_matches,
        events_without_resource=sum(1 for event in log.events if not event.resource),
        summary=summary,
    )


def _match(
    counts: Counter[str], targets: list[ModelElement], confirmed: dict[str, str | None] | None
) -> MatchReport:
    return apply_confirmed(counts, targets, confirmed) if confirmed is not None else suggest_matches(counts, targets)
