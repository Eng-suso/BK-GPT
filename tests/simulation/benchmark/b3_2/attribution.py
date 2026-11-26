"""B3.2: attribuzione delle attese per causa, solo dal log (caso, attivita', inizio, fine, risorsa).

Ricerca: niente codice esterno, solo la libreria standard (portabile nel prodotto, LIC-01).

Per ogni esecuzione con l'abilitazione osservabile, l'attesa e' l'intervallo fra la fine
dell'ultima attivita' del caso che la precede (non concorrente) e il suo inizio. La si
scompone guardando la risorsa che l'ha eseguita:

1. dall'inizio all'indietro, finche' la risorsa e' occupata in altro lavoro o fuori dal suo
   orario senza buchi, l'attivita' aspettava la risorsa: **congestione** (occupata) o
   **indisponibilita'** (fuori orario);
2. il resto, prima, e' tempo in cui l'attivita' era pronta e la risorsa no-ostacolo: un
   **ritardo esterno** (attese che il log non spiega: clienti, fornitori, sistemi);
3. se la risorsa ha avviato insieme piu' esecuzioni della stessa attivita', il ritardo
   esterno di quel gruppo e' **batching**.

Le **sospensioni** richiedono un ciclo di vita (sospeso/ripreso) che questi log non hanno:
la causa esiste ma qui non si osserva.

Orari delle risorse: scoperti dal log per gruppo di risorse con le stesse attivita',
su fasce orarie settimanali (``Calendar``).
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

WEEK = 7 * 86400
CAUSES = ("contention", "unavailability", "extraneous", "batching")


@dataclass(frozen=True, slots=True)
class Execution:
    case_id: str
    activity: str
    start: float  # secondi epoch
    end: float
    resource: str


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
            calendars[g] = Calendar(_merge([(s * slot, (s + 1) * slot) for s in sorted(on)]))
    return {r: calendars[g] for r, g in group_of.items()}


def _merge(periods: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
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
        return sum(self.seconds.values())

    def dominant(self, tolerance: float = 1.0) -> str:
        if self.total <= tolerance:
            return "none"
        return max(CAUSES, key=lambda c: self.seconds.get(c, 0.0))


class _Busy:
    """Gli intervalli di lavoro di una risorsa, uniti, per chiedere se e' occupata."""

    def __init__(self, intervals: list[tuple[float, float]]):
        self.intervals = _merge(intervals)
        self.starts = [lo for lo, _ in self.intervals]

    def covering(self, t: float, gap: float) -> tuple[float, float] | None:
        """L'intervallo di lavoro che contiene l'istante appena prima di ``t`` (entro ``gap``)."""
        k = bisect.bisect_left(self.starts, t) - 1
        if k >= 0:
            lo, hi = self.intervals[k]
            if hi >= t - gap:
                return lo, hi
        return None


def decompose(window: tuple[float, float], busy: _Busy, calendar: Calendar, *, gap: float) -> dict[str, float]:
    """Scompone ``[a, b]``: dalla fine all'indietro occupata/fuori orario senza buchi, poi ritardo esterno."""
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
    return {"contention": contention, "unavailability": unavailable, "extraneous": max(0.0, t - a), "batching": 0.0}


_EPS = 1e-3


def attribute(executions: Sequence[Execution], *, gap: float = 1.0, concurrency: float = 0.5,
              calendars: dict[str, Calendar] | None = None, batch_tolerance: float = 1.0) -> list[Waiting]:
    """Le attese di ogni esecuzione, per causa (secondi). ``calendars`` se gia' noti, altrimenti scoperti.

    Il lavoro della risorsa conta solo se iniziato prima dell'esecuzione: la propria e quelle
    avviate insieme (batch) non la occupano.
    """
    enabled = enablements(executions, concurrent_pairs(executions, concurrency))
    calendars = discover_calendars(executions) if calendars is None else calendars
    work: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in executions:
        work[e.resource].append((e.start, e.end))
    busy = {r: _Busy(intervals) for r, intervals in work.items()}
    batched = _batches(executions, batch_tolerance)
    result: list[Waiting] = []
    for i, e in enumerate(executions):
        if enabled[i] is None or enabled[i] >= e.start:
            result.append(Waiting(enabled[i], dict.fromkeys(CAUSES, 0.0)))
            continue
        seconds = decompose((enabled[i], e.start), busy[e.resource], calendars.get(e.resource, Calendar(always=True)), gap=gap)
        if i in batched:
            seconds["batching"], seconds["extraneous"] = seconds["extraneous"], 0.0
        result.append(Waiting(enabled[i], seconds))
    return result


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


# --------------------------------------------------------------------------- ritardi esterni per il simulatore


def extraneous_delays(executions: Sequence[Execution], waitings: Sequence[Waiting], *, min_share: float = 0.05) -> dict[str, dict]:
    """Per attivita' la distribuzione del ritardo esterno (formato Prosimos ``event_distribution``).

    Si considerano le esecuzioni con l'abilitazione osservabile, zeri compresi; un'attivita'
    ha un timer se piu' del ``min_share`` delle sue esecuzioni ha un ritardo (la stessa regola
    del lavoro di Chapela-Campa e Dumas). Il ritardo e' la quota ``extraneous`` (il batching no:
    lo spiega la risorsa).
    """
    values: dict[str, list[float]] = defaultdict(list)
    for e, w in zip(executions, waitings, strict=True):
        if w.enabled is not None:
            values[e.activity].append(w.seconds["extraneous"])
    delays = {}
    for activity, xs in values.items():
        if sum(x > 0 for x in xs) / len(xs) > min_share:
            delays[activity] = fit_duration(xs)
    return delays


def fit_duration(xs: Sequence[float]) -> dict:
    """Una distribuzione per Prosimos dai momenti: fissa, esponenziale o lognormale."""
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / max(1, n - 1)
    low, high = min(xs), max(xs)
    if mean <= 0 or var ** 0.5 < 0.01 * mean:
        return {"distribution_name": "fix", "distribution_params": [{"value": round(mean, 3)}]}
    cv = var ** 0.5 / mean
    if 0.8 <= cv <= 1.25:
        return {"distribution_name": "expon",
                "distribution_params": [{"value": round(mean, 3)}, {"value": round(low, 3)}, {"value": round(high, 3)}]}
    return {"distribution_name": "lognorm",
            "distribution_params": [{"value": round(mean, 3)}, {"value": round(var, 3)}, {"value": round(low, 3)}, {"value": round(high, 3)}]}


BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def add_timers(bpmn: str, delays: dict[str, dict]) -> tuple[str, list[dict]]:
    """Il BPMN con un timer prima di ogni attivita' con ritardo e la ``event_distribution`` dello scenario.

    Il timer prende il posto della freccia che entra nell'attivita' (una sola, come nei modelli
    di SIMOD); le attivita' con piu' frecce in ingresso restano senza timer.
    """
    import xml.etree.ElementTree as ET

    ET.register_namespace("", BPMN_NS)
    root = ET.fromstring(bpmn)
    q = lambda tag: f"{{{BPMN_NS}}}{tag}"  # noqa: E731
    process = root.find(q("process"))
    events = []
    for n, task in enumerate(process.findall(q("task"))):
        name = task.get("name")
        if name not in delays:
            continue
        incoming = [f for f in process.findall(q("sequenceFlow")) if f.get("targetRef") == task.get("id")]
        if len(incoming) != 1:
            continue
        timer_id, flow_id = f"Event_b32_{n}", f"Flow_b32_{n}"
        edge = incoming[0]
        edge.set("targetRef", timer_id)
        timer = ET.SubElement(process, q("intermediateCatchEvent"), {"id": timer_id})
        ET.SubElement(timer, q("incoming")).text = edge.get("id")
        ET.SubElement(timer, q("outgoing")).text = flow_id
        ET.SubElement(timer, q("timerEventDefinition"), {"id": f"TimerEventDefinition_b32_{n}"})
        ET.SubElement(process, q("sequenceFlow"), {"id": flow_id, "sourceRef": timer_id, "targetRef": task.get("id")})
        for inc in task.findall(q("incoming")):
            if inc.text == edge.get("id"):
                inc.text = flow_id
        events.append({"event_id": timer_id, "activity": name} | delays[name])
    return ET.tostring(root, encoding="unicode", xml_declaration=True), events
