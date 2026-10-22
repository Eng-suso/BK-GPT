"""I KPI di un event log ristretti ai casi iniziati in un periodo (SIM-28).

Per misurare un cambiamento introdotto in una data si confrontano i casi
iniziati prima con quelli iniziati dopo: un caso appartiene al periodo in cui
comincia (il suo primo evento), anche se finisce dopo. Lo stesso calcolo dei
KPI del log intero (``kpi.summarize``), sui soli casi del periodo.

Funzioni pure: il log in ingresso non cambia.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from backend.eventlog.model import CanonicalEvent, EventLog


def case_start(events: list[CanonicalEvent]) -> datetime:
    return min(event.start or event.end for event in events)


def cases_started(log: EventLog, *, since: date | None = None, before: date | None = None) -> EventLog:
    """Il log con i soli casi il cui primo evento cade in [``since``, ``before``)."""
    kept = {
        case_id for case_id, events in log.cases().items()
        if _within(case_start(events), since=since, before=before)
    }
    return replace(
        log,
        events=tuple(event for event in log.events if event.case_id in kept),
        case_attributes={case: values for case, values in log.case_attributes.items() if case in kept},
    )


def _within(moment: datetime, *, since: date | None, before: date | None) -> bool:
    # Un istante senza fuso e' preso come scritto; con il fuso si confronta in UTC.
    day = moment.astimezone(UTC).date() if moment.tzinfo is not None else moment.date()
    return (since is None or day >= since) and (before is None or day < before)
