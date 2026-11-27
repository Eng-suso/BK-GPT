"""Perche' si aspetta: le attese di un event log attribuite alla causa (VPT B3.2).

Solo dal log (caso, attivita', inizio, fine, risorsa), senza codice esterno. Per ogni
esecuzione con l'abilitazione osservabile l'attesa va dalla fine dell'ultima attivita' del
caso che la abilita (non concorrente) al suo inizio. Si scompone guardando la risorsa che
l'ha eseguita, dall'inizio all'indietro:

1. finche' la risorsa e' occupata in altro lavoro o fuori dal suo orario, senza buchi,
   l'attivita' aspettava la risorsa: **congestione** (occupata) o **indisponibilita'**
   (fuori orario);
2. il resto, prima, e' un **ritardo esterno**: l'attivita' era pronta e la risorsa non era l'ostacolo
   (clienti, fornitori, altri uffici, sistemi);
3. le esecuzioni avviate insieme dalla stessa risorsa sulla stessa attivita' sono un
   **batching**: il loro ritardo esterno e' l'attesa di riempire il lotto.

Le sospensioni richiedono un ciclo di vita (sospeso/ripreso) che i log importati non hanno.
Gli orari delle risorse si scoprono dal log per gruppo di risorse con le stesse attivita'.

Ricerca di B3.2, non ancora nel prodotto (il GO dei reali manca). Verifica (scheda 2 in ``docs/vpt/LOG.md``): sui 16 sintetici con timer di Chapela-Campa
e Dumas, rigenerati con la verita', la causa giusta nel 95,0% delle attese in validazione e nel
95,65% in test; ``tests/simulation/benchmark/b3_2/attribution_eval.py``.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Cause = Literal["contention", "unavailability", "extraneous", "batching"]

WEEK = 7 * 86400
CAUSES: tuple[Cause, ...] = ("contention", "unavailability", "extraneous", "batching")


@dataclass(frozen=True, slots=True)
class Execution:
    """Un'esecuzione del log. Gli istanti sono secondi su un asse continuo (epoch, o l'ora locale
    del log: vedi ``executions_of``); orari e settimane si leggono su quell'asse come UTC."""

    case_id: str
    activity: str
    start: float
    end: float
    resource: str  # "" se il log non la registra: l'esecuzione abilita le altre, la sua attesa non si spiega
    enabled: float | None = None  # l'abilitazione, se il log la registra


@dataclass(slots=True)
class Calendar:
    """Orario settimanale: intervalli ``[lo, hi)`` in secondi dall'inizio del lunedi' (UTC)."""

    periods: list[tuple[float, float]] = field(default_factory=list)
    always: bool = False

    def is_on(self, t: float) -> bool:
        if self.always:
            return True
        w = _week_offset(t)
        return any(lo <= w < hi for lo, hi in self.periods)

    def off_within(self, a: float, b: float) -> float:
        """Secondi fuori orario in ``[a, b]``."""
        if self.always or b <= a:
            return 0.0
        return (b - a) - self.on_within(a, b)

    def on_within(self, a: float, b: float) -> float:
        if self.always:
            return max(0.0, b - a)
        total = 0.0
        base = a - _week_offset(a)
        while base < b:
            for lo, hi in self.periods:
                total += max(0.0, min(b, base + hi) - max(a, base + lo))
            base += WEEK
        return total

    def last_on_before(self, t: float) -> float | None:
        """L'ultimo istante <= t in cui l'orario e' aperto (fine della fascia), o None entro due settimane."""
        if self.always or self.is_on(t):
            return t
        base = t - _week_offset(t)
        best = None
        for week in range(3):
            for _lo, hi in self.periods:
                end = base - week * WEEK + hi
                if end <= t and (best is None or end > best):
                    best = end
            if best is not None:
                return best
        return None


def _week_offset(t: float) -> float:
    moment = datetime.fromtimestamp(t, UTC)
    return moment.weekday() * 86400 + moment.hour * 3600 + moment.minute * 60 + moment.second + moment.microsecond / 1e6


# --------------------------------------------------------------------------- scoperta dal log


def concurrent_pairs(executions: Sequence[Execution], threshold: float = 0.5) -> set[frozenset[str]]:
    """Coppie di attivita' che si sovrappongono nello stesso caso in almeno ``threshold`` dei casi con entrambe."""
    by_case: dict[str, list[Execution]] = defaultdict(list)
    for e in executions:
        by_case[e.case_id].append(e)
    together: dict[frozenset[str], int] = defaultdict(int)
    overlapping: dict[frozenset[str], int] = defaultdict(int)
    for events in by_case.values():
        acts = sorted({e.activity for e in events})
        seen_overlap: set[frozenset[str]] = set()
        for i, x in enumerate(events):
            for y in events[i + 1:]:
                if x.activity != y.activity and x.start < y.end and y.start < x.end:
                    seen_overlap.add(frozenset((x.activity, y.activity)))
        for i, a in enumerate(acts):
            for b in acts[i + 1:]:
                together[frozenset((a, b))] += 1
        for pair in seen_overlap:
            overlapping[pair] += 1
    return {pair for pair, n in together.items() if overlapping[pair] / n >= threshold}


def enablements(executions: Sequence[Execution], concurrent: set[frozenset[str]]) -> list[float | None]:
    """Per ogni esecuzione la fine dell'ultima attivita' del caso che la abilita (None se e' la prima)."""
    by_case: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(executions):
        by_case[e.case_id].append(i)
    enabled: list[float | None] = [None] * len(executions)
    for indexes in by_case.values():
        for i in indexes:
            e = executions[i]
            if e.enabled is not None:
                enabled[i] = min(e.enabled, e.start)
                continue
            best = None
            for j in indexes:
                p = executions[j]
                if j == i or p.end > e.start or frozenset((p.activity, e.activity)) in concurrent:
                    continue
                if p.end == e.start and p.start == e.start and p.activity == e.activity:
                    continue
                if best is None or p.end > best:
                    best = p.end
            enabled[i] = best
    return enabled


def resource_groups(executions: Sequence[Execution]) -> dict[str, str]:
    """Risorsa -> gruppo: le risorse che eseguono lo stesso insieme di attivita'."""
    activities: dict[str, set[str]] = defaultdict(set)
    for e in executions:
        if e.resource:
            activities[e.resource].add(e.activity)
    return {r: "|".join(sorted(acts)) for r, acts in activities.items()}


def discover_calendars(executions: Sequence[Execution], *, slot: int = 3600, support: float = 0.1,
                       fill_day: bool = True) -> dict[str, Calendar]:
    """Orari per risorsa, scoperti per gruppo: una fascia e' aperta se il gruppo ci lavora in
    almeno ``support`` delle settimane in cui e' attivo; con ``fill_day`` le fasce di un giorno
    fra la prima e l'ultima aperta si aprono (giornata lavorativa senza buchi)."""
    group_of = resource_groups(executions)
    weeks: dict[str, set[int]] = defaultdict(set)
    slots: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    per_day = 86400 // slot
    for e in executions:
        if not e.resource:
            continue
        g = group_of[e.resource]
        for t in (e.start, e.end):
            week = int((t - _week_offset(t)) // WEEK)
            weeks[g].add(week)
            slots[g][int(_week_offset(t) // slot)].add(week)
    calendars: dict[str, Calendar] = {}
    for g in weeks:
        on = {s for s, seen in slots[g].items() if len(seen) / len(weeks[g]) >= support}
        if fill_day:
            for day in range(7):
                today = [s for s in on if s // per_day == day]
                if today:
                    on |= set(range(min(today), max(today) + 1))
        if len(on) == 7 * per_day:
            calendars[g] = Calendar(always=True)
        else:
            calendars[g] = Calendar(merge_periods([(s * slot, (s + 1) * slot) for s in sorted(on)]))
    return {r: calendars[g] for r, g in group_of.items()}


def merge_periods(periods: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for lo, hi in sorted(periods):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


# --------------------------------------------------------------------------- scomposizione


@dataclass(frozen=True, slots=True)
class Waiting:
    enabled: float | None
    seconds: dict[str, float]

    @property
    def total(self) -> float:
        return sum(self.seconds.get(c, 0.0) for c in CAUSES)

    def dominant(self, tolerance: float = 1.0) -> str:
        if self.total <= tolerance:
            return "none"
        return max(CAUSES, key=lambda c: self.seconds.get(c, 0.0))


class BusyPeriods:
    """Gli intervalli di lavoro di una risorsa, uniti, per chiedere se e' occupata."""

    def __init__(self, intervals: list[tuple[float, float]]):
        self.intervals = merge_periods(intervals)
        self.starts = [lo for lo, _ in self.intervals]

    def covering(self, t: float, gap: float) -> tuple[float, float] | None:
        """L'intervallo di lavoro che contiene l'istante appena prima di ``t`` (entro ``gap``)."""
        k = bisect.bisect_left(self.starts, t) - 1
        if k >= 0:
            lo, hi = self.intervals[k]
            if hi >= t - gap:
                return lo, hi
        return None


def decompose(window: tuple[float, float], busy: BusyPeriods, calendar: Calendar, *, gap: float,
              simulator_shares: bool = False) -> dict[str, float]:
    """Scompone ``[a, b]``: dalla fine all'indietro occupata/fuori orario senza buchi, poi ritardo esterno.

    Con ``simulator_shares`` aggiunge ``idle`` e ``on_shift``: del ritardo esterno, i secondi con la
    risorsa libera e in orario e quelli in orario. Non sono cause: servono agli scenari di ricerca
    di B3.2 (v2-v5) e costano un giro sul lavoro della risorsa.
    """
    a, b = window
    t = b
    contention = unavailable = 0.0
    while t > a:
        piece = busy.covering(t, gap)
        if piece is not None and piece[0] < t:
            lo = max(a, piece[0])
            off = calendar.off_within(lo, t)
            unavailable += off
            contention += (t - lo) - off
            t = lo
        elif not calendar.is_on(t - _EPS):
            on = calendar.last_on_before(t - _EPS)
            lo = a if on is None else max(a, on)
            unavailable += t - lo
            t = lo
        else:
            break
    extraneous = max(0.0, t - a)
    seconds = {"contention": contention, "unavailability": unavailable, "extraneous": extraneous, "batching": 0.0}
    if simulator_shares:
        on_shift = calendar.on_within(a, t) if extraneous else 0.0
        seconds["idle"] = max(0.0, on_shift - _busy_within(busy, a, t, calendar)) if extraneous else 0.0
        seconds["on_shift"] = on_shift
    return seconds


def _busy_within(busy: BusyPeriods, a: float, b: float, calendar: Calendar) -> float:
    """Secondi in orario in cui la risorsa lavora in ``[a, b]``."""
    k = max(0, bisect.bisect_right(busy.starts, a) - 1)
    total = 0.0
    for lo, hi in busy.intervals[k:]:
        if lo >= b:
            break
        lo, hi = max(lo, a), min(hi, b)
        if lo < hi:
            total += calendar.on_within(lo, hi)
    return total


_EPS = 1e-3


def attribute(executions: Sequence[Execution], *, gap: float = 1.0, concurrency: float = 0.5,
              calendars: dict[str, Calendar] | None = None, batch_tolerance: float = 1.0,
              simulator_shares: bool = False) -> list[Waiting]:
    """Le attese di ogni esecuzione, per causa (secondi). ``calendars`` se gia' noti, altrimenti scoperti.

    Il lavoro della risorsa conta solo se iniziato prima dell'esecuzione: la propria e quelle
    avviate insieme (batch) non la occupano. Un'esecuzione senza risorsa abilita le altre ma la
    sua attesa non si spiega (``enabled`` None). Se gli inizi sono registrati al minuto (quasi
    tutti a secondi zero) il batching non si cerca: esecuzioni diverse avrebbero lo stesso inizio.
    """
    enabled = enablements(executions, concurrent_pairs(executions, concurrency))
    calendars = discover_calendars(executions) if calendars is None else calendars
    work: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in executions:
        if e.resource:
            work[e.resource].append((e.start, e.end))
    busy = {r: BusyPeriods(intervals) for r, intervals in work.items()}
    batched = {} if _minute_resolution(executions) else _batches(executions, batch_tolerance)
    result: list[Waiting] = []
    for i, e in enumerate(executions):
        if not e.resource:
            result.append(Waiting(None, dict.fromkeys(CAUSES, 0.0)))
            continue
        if enabled[i] is None or enabled[i] >= e.start:
            result.append(Waiting(enabled[i], dict.fromkeys(CAUSES, 0.0)))
            continue
        seconds = decompose((enabled[i], e.start), busy[e.resource], calendars.get(e.resource, Calendar(always=True)), gap=gap,
                            simulator_shares=simulator_shares)
        if i in batched:
            seconds["batching"], seconds["extraneous"] = seconds["extraneous"], 0.0
            if simulator_shares:
                seconds["idle"] = seconds["on_shift"] = 0.0
        result.append(Waiting(enabled[i], seconds))
    return result


def _minute_resolution(executions: Sequence[Execution], share: float = 0.95) -> bool:
    """Inizi registrati al minuto: quasi tutti cadono a secondi zero."""
    starts = [e.start for e in executions if e.resource]
    return bool(starts) and sum(s % 60 == 0 for s in starts) / len(starts) >= share


def _batches(executions: Sequence[Execution], tolerance: float) -> dict[int, int]:
    """Esecuzioni avviate insieme (entro ``tolerance``) dalla stessa risorsa sulla stessa attivita'."""
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, e in enumerate(executions):
        by_key[(e.resource, e.activity)].append(i)
    batched: dict[int, int] = {}
    group = 0
    for indexes in by_key.values():
        indexes.sort(key=lambda i: executions[i].start)
        run = [indexes[0]] if indexes else []
        for i in indexes[1:]:
            if executions[i].start - executions[run[-1]].start <= tolerance:
                run.append(i)
                continue
            if len(run) > 1:
                batched.update({j: group for j in run})
                group += 1
            run = [i]
        if len(run) > 1:
            batched.update({j: group for j in run})
            group += 1
    return batched
