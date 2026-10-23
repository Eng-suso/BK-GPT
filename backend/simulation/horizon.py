"""Un periodo da simulare invece di un numero di casi (SIM-03, orizzonte a tempo).

Prosimos 2.1 si ferma quando ha generato ``total_cases`` casi e li porta tutti
a termine: non sa "simula quattro settimane". Il periodo si ottiene tagliando
il log, ed e' esatto: un evento prima della fine del periodo dipende solo dai
casi arrivati prima, quindi i casi che il motore genera dopo non cambiano
niente dentro il periodo. Servono abbastanza casi perche' gli arrivi coprano
il periodo: si stimano dal ritmo e dal calendario degli arrivi, con margine, e
il riepilogo dice se la copertura c'e' stata.

A fine periodo i casi si dividono in completati (misurati dai KPI) e ancora
aperti (arrivati ma non finiti): i secondi sono il lavoro in corso che il
periodo lascia, il dato che con un numero di casi non esisteva.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from backend.simulation.ir.model import (
    CalendarPeriod,
    Exponential,
    Fixed,
    Gamma,
    LogNormal,
    Normal,
    SimulationModel,
    Uniform,
)

if TYPE_CHECKING:
    from backend.simulation.log_processor import LogEvent

_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_WEEK = 7 * 86_400
# Il motore deve generare arrivi oltre la fine del periodo: la stima e' una
# media, e la coda della distribuzione puo' rallentarli.
MARGIN = 1.5
MAX_CASES = 100_000


def horizon_start(start_date: str | None, *, today: datetime | None = None) -> str:
    """L'inizio del periodo: quello chiesto, o la mezzanotte UTC di oggi.

    Fissato a mezzanotte e non all'istante: lo stesso invio ritentato nella
    giornata ritrova lo stesso run.
    """
    if start_date:
        return start_date
    now = today or datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def horizon_end(start_date: str, days: int) -> float:
    """La fine del periodo, in secondi epoch come gli eventi del log."""
    return (_parse(start_date) + timedelta(days=days)).timestamp()


def horizon_cases(model: SimulationModel, start_date: str, days: int) -> int:
    """Quanti casi chiedere al motore perche' gli arrivi coprano il periodo."""
    start = _parse(start_date)
    end = start + timedelta(days=days)
    arrival = model.arrival
    bands = model.arrival_bands()
    if bands:
        # SIM-08b: una fascia sta in un giorno, quindi ogni apertura e' in un solo mese.
        factors = {m.month: m.factor for m in arrival.months}
        expected = sum(
            (high - low) / band.mean_seconds * factors.get((start + timedelta(seconds=low)).month, 1.0)
            for band in bands
            for low, high in _occurrences(start, end, [band])
        )
    else:
        calendar = next(c for c in model.calendars if c.id == arrival.calendar_id)
        mean = _mean(arrival.interarrival)
        # Un arrivo che cade a calendario chiuso slitta all'apertura: uno in piu' per apertura.
        expected = _open_seconds(start, end, calendar.periods) / mean + _openings(start, end, calendar.periods)
    cases = math.ceil(expected * MARGIN) + 30
    if cases > MAX_CASES:
        raise ValueError(
            f"Con questo ritmo degli arrivi {days} giorni sono circa {math.ceil(expected)} casi: "
            f"il massimo è {MAX_CASES // 1000}.000 con il margine. Accorcia il periodo."
        )
    return cases


@dataclass(frozen=True, slots=True)
class HorizonOutcome:
    """Il periodo come lo salva il riepilogo del run."""

    days: int
    arrived_cases: int
    completed_cases: int
    open_cases: int
    # Falso se il motore ha smesso di generare arrivi prima della fine del
    # periodo: i KPI valgono, ma per meno arrivi di quanti il periodo ne avrebbe.
    covered: bool


def within_horizon(events: list[LogEvent], end: float, days: int) -> tuple[list[LogEvent], list[LogEvent], HorizonOutcome]:
    """Gli eventi dei casi completati entro ``end``, quelli dei casi arrivati prima, e l'esito."""
    first: dict[str, float] = {}
    last: dict[str, float] = {}
    for ev in events:
        first[ev.case_id] = min(first.get(ev.case_id, ev.enable), ev.enable)
        last[ev.case_id] = max(last.get(ev.case_id, ev.end), ev.end)
    arrived = {case_id for case_id, at in first.items() if at < end}
    completed = {case_id for case_id in arrived if last[case_id] <= end}
    outcome = HorizonOutcome(
        days=days,
        arrived_cases=len(arrived),
        completed_cases=len(completed),
        open_cases=len(arrived) - len(completed),
        covered=len(arrived) < len(first),
    )
    return (
        [ev for ev in events if ev.case_id in completed],
        [ev for ev in events if ev.case_id in arrived],
        outcome,
    )


def _mean(distribution) -> float:
    if isinstance(distribution, Fixed):
        return distribution.value
    if isinstance(distribution, Uniform):
        return (distribution.minimum + distribution.maximum) / 2
    if isinstance(distribution, (Exponential, Normal, LogNormal, Gamma)):
        return distribution.mean
    raise TypeError(f"distribuzione senza media: {distribution!r}")  # pragma: no cover


def _weekly(periods) -> list[tuple[float, float]]:
    """I periodi come intervalli della settimana, in secondi da lunedi' 00:00."""
    intervals = []
    for period in periods:
        first, last = _DAYS.index(period.from_day), _DAYS.index(period.to_day)
        days = range(first, last + 1) if first <= last else [*range(first, 7), *range(0, last + 1)]
        begin, end = _clock(period.begin), _clock(period.end)
        intervals.extend((day * 86_400 + begin, day * 86_400 + end) for day in days)
    return intervals


def _occurrences(start: datetime, end: datetime, periods) -> list[tuple[float, float]]:
    """Le aperture del calendario fra ``start`` e ``end``, tagliate ai bordi, in secondi da ``start``."""
    monday = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=start.weekday())
    origin, horizon = (start - monday).total_seconds(), (end - monday).total_seconds()
    weekly = _weekly(periods)
    found = []
    for week in range(int(horizon // _WEEK) + 1):
        for begin, finish in weekly:
            low, high = max(origin, begin + week * _WEEK), min(horizon, finish + week * _WEEK)
            if low < high:
                found.append((low - origin, high - origin))
    return found


def _open_seconds(start: datetime, end: datetime, periods: list[CalendarPeriod] | tuple[CalendarPeriod, ...]) -> float:
    return sum(high - low for low, high in _occurrences(start, end, periods))


def _openings(start: datetime, end: datetime, periods) -> int:
    return len(_occurrences(start, end, periods))


def _clock(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
