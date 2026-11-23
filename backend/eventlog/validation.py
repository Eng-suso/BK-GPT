"""Confronto di un log osservato con repliche indipendenti dello stesso scenario.

La vista confrontabile parte dal primo inizio osservato. L'intervallo fra
attivita' usa su entrambi i lati la fine dell'evento precedente; non pretende
di separare coda risorsa, ritardi esterni e tempo prima del primo evento.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from statistics import mean, stdev

from backend.eventlog.model import EventLog


@dataclass(frozen=True)
class _Measures:
    cycle: list[float]
    between: list[float]
    processing: list[float]
    throughput: float
    first_wait: float | None
    grams: Counter[tuple[str, str]]


def _measure(log: EventLog) -> _Measures:
    cycles: list[float] = []
    between: list[float] = []
    processing: list[float] = []
    first_wait: list[float] = []
    grams: Counter[tuple[str, str]] = Counter()
    first_starts = []
    last_ends = []
    for events in log.cases().values():
        if not events or any(event.start is None for event in events):
            raise ValueError("Ogni evento deve avere un timestamp di inizio per la validazione temporale.")
        ordered = sorted(events, key=lambda event: (event.start, event.end))
        first = ordered[0]
        first_starts.append(first.start)
        last_ends.append(max(event.end for event in ordered))
        cycles.append((last_ends[-1] - first.start).total_seconds())
        processing.append(sum(max(0.0, (event.end - event.start).total_seconds()) for event in ordered))
        previous_end = first.end
        gap = 0.0
        for event in ordered[1:]:
            gap += max(0.0, (event.start - previous_end).total_seconds())
            previous_end = max(previous_end, event.end)
        between.append(gap)
        if first.enabled is not None:
            first_wait.append(max(0.0, (first.start - first.enabled).total_seconds()))
        trace = ["<START>", *(event.activity for event in ordered), "<END>"]
        grams.update(zip(trace, trace[1:], strict=False))
    span = (max(last_ends) - min(first_starts)).total_seconds() if cycles else 0.0
    return _Measures(cycles, between, processing, len(cycles) * 3600 / span if span > 0 else 0.0,
                     mean(first_wait) if first_wait else None, grams)


def _wasserstein(a: list[float], b: list[float]) -> float:
    """Empirical W1, integrated exactly over the two quantile step functions."""
    a, b = sorted(a), sorted(b)
    i = j = 0
    position = total = 0.0
    while i < len(a) and j < len(b):
        boundary = min((i + 1) / len(a), (j + 1) / len(b))
        total += (boundary - position) * abs(a[i] - b[j])
        position = boundary
        if position >= (i + 1) / len(a) - 1e-12:
            i += 1
        if position >= (j + 1) / len(b) - 1e-12:
            j += 1
    return total


def _ngd(a: Counter[tuple[str, str]], b: Counter[tuple[str, str]]) -> float:
    denominator = sum(a.values()) + sum(b.values())
    return sum(abs(a[key] - b[key]) for key in a.keys() | b.keys()) / denominator if denominator else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower)


def _interval(values: list[float]) -> dict:
    # t(0.975, df) for df 1..19; larger groups use the conservative df=19 value.
    t = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262,
         2.228, 2.201, 2.179, 2.16, 2.145, 2.131, 2.12, 2.11, 2.101, 2.093, 2.086)
    return {"mean": mean(values), "ci95Half": t[min(len(values) - 2, 19)] * stdev(values) / sqrt(len(values)) if len(values) > 1 else None,
            "min": min(values), "max": max(values)}


def validate(real: EventLog, simulated: list[tuple[int, EventLog]]) -> dict:
    if not simulated:
        raise ValueError("Servono repliche simulate complete.")
    reference = _measure(real)
    if not reference.cycle:
        raise ValueError("Il log reale deve avere inizio e fine per ogni evento confrontato.")
    measured = [(run_id, _measure(log)) for run_id, log in simulated]
    if any(not item.cycle for _, item in measured):
        raise ValueError("Una replica non contiene casi completi con inizio e fine.")
    values: dict[str, tuple[float, list[float]]] = {
        "cycle": (mean(reference.cycle), [mean(item.cycle) for _, item in measured]),
        "p50": (_percentile(reference.cycle, 0.5), [_percentile(item.cycle, 0.5) for _, item in measured]),
        "p90": (_percentile(reference.cycle, 0.9), [_percentile(item.cycle, 0.9) for _, item in measured]),
        "between": (mean(reference.between), [mean(item.between) for _, item in measured]),
        "processing": (mean(reference.processing), [mean(item.processing) for _, item in measured]),
        "throughput": (reference.throughput, [item.throughput for _, item in measured]),
    }
    kpis = {key: {"real": actual, **_interval(samples),
                  "bias": mean(samples) - actual,
                  "mae": mean(abs(value - actual) for value in samples)}
            for key, (actual, samples) in values.items()}
    distances = {
        "cycleW1": _interval([_wasserstein(reference.cycle, item.cycle) for _, item in measured]),
        "ngd": _interval([_ngd(reference.grams, item.grams) for _, item in measured]),
    }
    pooled_cycles = [cycle for _, item in measured for cycle in item.cycle]
    return {"referenceCases": len(reference.cycle), "simulatedCases": [len(item.cycle) for _, item in measured],
            "replications": len(measured),
            "runIds": [run_id for run_id, _ in measured], "kpis": kpis, "distances": distances,
            "pooledCycle": {"p50": _percentile(pooled_cycles, 0.5), "p90": _percentile(pooled_cycles, 0.9)},
            "firstWaitSimulated": _interval([item.first_wait for _, item in measured if item.first_wait is not None])
            if all(item.first_wait is not None for _, item in measured) else None,
            "basis": "first_observed_start_and_between_activities"}
