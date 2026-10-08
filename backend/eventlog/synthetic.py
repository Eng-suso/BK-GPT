"""Il log che produce una simulazione, nella forma dell'event log canonico.

Il CSV di Prosimos passa intero: ``enable_time`` diventa ``enabled`` (senza,
l'attesa prima della prima attivita' di un caso andrebbe persa). La risorsa e'
l'istanza del motore (``Operatore_0``) e il ruolo e' il suo pool (``Operatore``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.eventlog.model import CanonicalEvent, EventLog
from backend.simulation.log_processor import LogEvent, parse_prosimos_log, pool_key


def from_log_events(events: list[LogEvent], *, source_name: str | None = None) -> EventLog:
    canonical = tuple(
        CanonicalEvent(
            case_id=ev.case_id,
            activity=ev.activity,
            start=_utc(ev.start),
            enabled=_utc(ev.enable),
            end=_utc(ev.end),
            resource=ev.resource or None,
            role=pool_key(ev.resource) if ev.resource else None,
        )
        for ev in events
    )
    return EventLog(origin="simulated", events=canonical, source_name=source_name)


def from_prosimos_csv(csv_text: str, *, source_name: str | None = None) -> EventLog:
    """Il CSV di Prosimos come ``EventLog`` simulato. Alza ``ProsimosLogError`` se non si legge."""
    return from_log_events(parse_prosimos_log(csv_text), source_name=source_name)


def _utc(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)
