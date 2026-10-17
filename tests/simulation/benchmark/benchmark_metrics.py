"""SIM-36: le metriche del DeliR Simulation Benchmark.

Il twin impara dal periodo A e prevede il periodo B; si misura la previsione
contro il B reale, mai contro A. Le metriche confrontano due ``EventLog``
canonici (``backend/eventlog``), quindi valgono per un log simulato da
Prosimos come per la previsione piu' semplice, il gemello ingenuo "B sara'
come A" (``naive_prediction``), che e' la baseline da battere.

Sei metriche si calcolano dai log; le tre di efficienza e semplicita' (tempo
di calibrazione, di simulazione, di configurazione umana) si misurano fuori,
con l'orologio, e le scrive ``run_baseline``.

- distribuzioni (cycle, waiting): distanza di Wasserstein-1 fra le due
  distribuzioni empiriche, divisa per la media reale. 0 = identiche; 0,25 =
  in media un quarto della durata reale di scarto. Guarda la forma intera, non
  solo le medie;
- throughput: errore relativo sui casi completati al giorno;
- percorsi: distanza di variazione totale fra le frequenze delle varianti
  (0 = stesse varianti nelle stesse quote, 1 = nessuna in comune);
- risorse: variazione totale fra le quote di lavoro per risorsa. Senza
  calendari di disponibilita' l'utilizzo vero non si misura: si confronta come
  si divide il lavoro, non quanto e' carica ogni persona;
- obiettivo di servizio: scarto in punti percentuali fra la quota di casi entro
  il tempo prevista e quella osservata.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from backend.eventlog.kpi import to_log_events
from backend.eventlog.model import EventLog

SECONDS_PER_DAY = 86_400.0


def split_by_case_start(log: EventLog, cutoff: datetime) -> tuple[EventLog, EventLog]:
    """Periodo A (casi iniziati prima di ``cutoff``) e periodo B (gli altri)."""
    starts = {case: min(e.start or e.end for e in events) for case, events in log.cases().items()}
    in_a = {case for case, start in starts.items() if start < cutoff}

    def keep(cases: set[str], period: str) -> EventLog:
        return EventLog(
            origin=log.origin,
            events=tuple(e for e in log.events if e.case_id in cases),
            case_attributes={c: a for c, a in log.case_attributes.items() if c in cases},
            source_name=f"{log.source_name or 'log'} · {period}",
        )

    return keep(in_a, "A"), keep(set(starts) - in_a, "B")


def median_case_start(log: EventLog) -> datetime:
    """Il taglio che divide i casi a meta' per inizio: A e B con lo stesso numero di casi."""
    starts = sorted(min(e.start or e.end for e in events) for events in log.cases().values())
    if len(starts) < 2:
        raise ValueError("Servono almeno due casi per dividere il log in due periodi.")
    return starts[len(starts) // 2]


def cycle_times(log: EventLog) -> list[float]:
    """Durata di ogni caso in secondi, dal primo inizio all'ultima fine."""
    return [
        (max(e.end for e in events) - min(e.start or e.end for e in events)).total_seconds()
        for events in log.cases().values()
    ]


def waiting_times(log: EventLog) -> list[float]:
    """Attesa di ogni esecuzione in secondi, con l'abilitazione ricavata come nei KPI."""
    return [max(0.0, event.start - event.enable) for event in to_log_events(log)]


def daily_throughput(log: EventLog) -> float:
    """Casi completati al giorno sull'arco del log."""
    ends = [max(e.end for e in events) for events in log.cases().values()]
    if not ends:
        return 0.0
    span = (max(ends) - min(ends)).total_seconds() / SECONDS_PER_DAY
    return len(ends) / max(span, 1.0)


def variants(log: EventLog) -> Counter[tuple[str, ...]]:
    return Counter(tuple(e.activity for e in events) for events in log.cases().values())


def workload_shares(log: EventLog) -> dict[str, float]:
    """Quota del tempo di lavorazione di ogni risorsa sul totale."""
    busy: Counter[str] = Counter()
    for event in to_log_events(log):
        if event.resource:
            busy[event.resource] += max(0.0, event.end - event.start)
    total = sum(busy.values())
    return {resource: value / total for resource, value in busy.items()} if total > 0 else {}


def share_within(values: list[float], target_seconds: float) -> float:
    return sum(1 for v in values if v <= target_seconds) / len(values) if values else 0.0


def wasserstein(a: list[float], b: list[float], points: int = 1000) -> float:
    """Distanza di Wasserstein-1 fra due campioni, come integrale fra le funzioni quantile."""
    if not a or not b:
        raise ValueError("Servono due campioni non vuoti.")
    sa, sb = sorted(a), sorted(b)

    def quantile(sample: list[float], u: float) -> float:
        return sample[min(int(u * len(sample)), len(sample) - 1)]

    return sum(abs(quantile(sa, (i + 0.5) / points) - quantile(sb, (i + 0.5) / points)) for i in range(points)) / points


def relative_wasserstein(predicted: list[float], real: list[float]) -> float:
    mean = sum(real) / len(real) if real else 0.0
    distance = wasserstein(predicted, real)
    return distance / mean if mean > 0 else distance


def total_variation(p: dict, q: dict) -> float:
    """Meta' della somma degli scarti assoluti fra due distribuzioni di frequenze."""
    sp, sq = sum(p.values()), sum(q.values())
    if sp <= 0 or sq <= 0:
        return 1.0
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0) / sp - q.get(k, 0) / sq) for k in keys)


@dataclass(frozen=True, slots=True)
class FidelityMetrics:
    cycle_time_distribution: float
    waiting_time_distribution: float
    throughput_error: float
    path_frequency_distance: float
    resource_workload_error: float
    sla_prediction_error_pp: float
    sla_target_seconds: float

    def as_dict(self) -> dict[str, float]:
        return {name: round(getattr(self, name), 6) for name in self.__slots__}


def compare(predicted: EventLog, real: EventLog, *, sla_target_seconds: float) -> FidelityMetrics:
    """Le sei metriche calcolabili dai log: previsione di B contro il B reale."""
    if not predicted.events or not real.events:
        raise ValueError("La previsione e il log reale devono avere eventi.")
    real_throughput = daily_throughput(real)
    predicted_cycles, real_cycles = cycle_times(predicted), cycle_times(real)
    return FidelityMetrics(
        cycle_time_distribution=relative_wasserstein(predicted_cycles, real_cycles),
        waiting_time_distribution=relative_wasserstein(waiting_times(predicted), waiting_times(real)),
        throughput_error=abs(daily_throughput(predicted) - real_throughput) / real_throughput if real_throughput else 0.0,
        path_frequency_distance=total_variation(variants(predicted), variants(real)),
        resource_workload_error=total_variation(workload_shares(predicted), workload_shares(real)),
        sla_prediction_error_pp=100 * abs(share_within(predicted_cycles, sla_target_seconds) - share_within(real_cycles, sla_target_seconds)),
        sla_target_seconds=sla_target_seconds,
    )


def default_sla_target(calibration: EventLog, quantile: float = 0.8) -> float:
    """L'obiettivo di servizio del benchmark: l'80% dei casi di A entro questo tempo."""
    cycles = sorted(cycle_times(calibration))
    if not cycles:
        raise ValueError("Il periodo di calibrazione non ha casi.")
    return cycles[min(int(quantile * len(cycles)), len(cycles) - 1)]


def naive_prediction(calibration: EventLog) -> EventLog:
    """Il gemello ingenuo: "B sara' come A". La baseline che ogni twin deve battere."""
    return EventLog(origin="simulated", events=calibration.events, case_attributes=calibration.case_attributes, source_name="naive: B = A")
