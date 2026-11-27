"""B3.1: le varianti degli arrivi, ognuna con la sua scheda in ``docs/vpt/LOG.md``.

Una variante riceve la fase preparata da ``g3b/run.py`` (l'input della discovery, il numero
dei casi da prevedere e il loro primo inizio, il fuso del log) e restituisce gli istanti di
arrivo di una replica, tanti quanti i casi, mai prima del primo inizio. Del periodo da
prevedere sa solo questo, come ogni strumento di G3b.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from tests.simulation.benchmark.log_distance import Event, cases

# Sotto questi giorni interi nell'input non si ricampiona per giorno della settimana (C2).
WEEKDAY_MIN_FULL_DAYS = 7
DAY_MIN_FULL_DAYS = 2
# C3: i giorni donatori sono solo gli ultimi giorni interi dell'input, quattro per giorno della settimana.
RECENT_FULL_DAYS = 28


class Phase(Protocol):
    """Quello che una variante legge della fase preparata (``g3b.run.Prepared``)."""

    source_events: list[Event]
    cases: int
    start: datetime
    zone: ZoneInfo


@dataclass(frozen=True, slots=True)
class Variant:
    label: str
    build: Callable[[Phase, int], list[datetime]]  # (fase preparata, seed della replica) -> arrivi


def case_starts(events: Sequence[Event]) -> list[datetime]:
    """L'arrivo di ogni caso: il suo primo inizio, come lo misura CAR."""
    return sorted(min(e.start for e in group) for group in cases(events).values())


def day_blocks(phase: Phase, seed: int, recent: int | None = None) -> list[datetime]:
    """C2: giorni interi dell'input ricampionati dal primo inizio del periodo da prevedere.

    Ogni giorno del periodo prende gli arrivi (ora locale) di un giorno intero dell'input
    estratto a caso con lo stesso giorno della settimana; si va avanti finche' i casi non
    sono tutti arrivati. Il primo e l'ultimo giorno dell'input sono parziali e non si
    estraggono. Con meno di 7 giorni interi si estrae fra tutti, senza guardare il giorno
    della settimana; con meno di 2 (log di poche ore) si ricampionano i tempi fra arrivi.
    Con ``recent`` (C3) si estrae solo fra gli ultimi ``recent`` giorni interi dell'input.
    """
    starts = case_starts(phase.source_events)
    by_day: dict[date, list[timedelta]] = {}
    for instant in starts:
        local = instant.astimezone(phase.zone)
        by_day.setdefault(local.date(), []).append(local - _midnight(local.date(), phase.zone))
    first, last = min(by_day), max(by_day)
    full = [first + timedelta(days=n) for n in range(1, (last - first).days)]
    if recent is not None:
        full = full[-recent:]
    if len(full) < DAY_MIN_FULL_DAYS or not any(by_day.get(d) for d in full):
        return gap_bootstrap(starts, phase, seed)
    donors = {w: [d for d in full if d.weekday() == w] for w in range(7)} if len(full) >= WEEKDAY_MIN_FULL_DAYS else {}
    rng = random.Random(seed)
    arrivals: list[datetime] = []
    day = phase.start.astimezone(phase.zone).date()
    while len(arrivals) < phase.cases:
        donor = rng.choice(donors.get(day.weekday()) or full)
        midnight = _midnight(day, phase.zone)
        arrivals += [i for i in (midnight + offset for offset in by_day.get(donor, [])) if i >= phase.start]
        day += timedelta(days=1)
    return [a.astimezone(UTC) for a in sorted(arrivals)[: phase.cases]]


def recent_day_blocks(phase: Phase, seed: int) -> list[datetime]:
    """C3: come C2, con i giorni donatori presi solo dalle ultime quattro settimane intere."""
    return day_blocks(phase, seed, recent=RECENT_FULL_DAYS)


def gap_bootstrap(starts: list[datetime], phase: Phase, seed: int) -> list[datetime]:
    """Tempi fra arrivi dell'input estratti con reinserimento, dal primo inizio."""
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)] or [timedelta(0)]
    rng = random.Random(seed)
    arrivals = [phase.start]
    while len(arrivals) < phase.cases:
        arrivals.append(arrivals[-1] + rng.choice(gaps))
    return [a.astimezone(UTC) for a in arrivals]


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    """La mezzanotte locale: gli orari del giorno donatore restano orari locali."""
    return datetime.combine(day, time(0), zone)


VARIANTS: dict[str, Variant] = {
    "simod_extr_days": Variant("SIMOD con ritardi estranei + giorni dell'input ricampionati (B3.1-C2)", day_blocks),
    "simod_extr_recent": Variant(
        "SIMOD con ritardi estranei + giorni delle ultime 4 settimane dell'input ricampionati (B3.1-C3)", recent_day_blocks),
}
