"""B2: le distanze fra event log di ``log-distance-measures`` 2.2, portate qui.

Sono le misure del paper sui ritardi estranei (Chapela-Campa e Dumas, 2024) e di
SIMOD. La libreria vuole Python 3.11 o 3.12 e scipy; il backend e' sulla 3.14
senza scipy, quindi le formule sono riscritte qui, con i parametri di default
che usano il paper e SIMOD. ``test_log_distance.py`` controlla che diano gli
stessi numeri della libreria (``log_distance_reference.py`` li rigenera).

Fonte: github.com/AutomatedProcessImprovement/log-distance-measures, tag 2.2.0,
Copyright David Chapela de la Campa, licenza Apache 2.0.

Tutte le distanze temporali sono Wasserstein-1 fra istanti o durate ridotti a
bin interi di un'ora: il risultato e' in ore.

- ``cycle_time_w1``: durate dei casi, dal primo inizio all'ultima fine;
- ``ngram``: frequenze dei 3-grammi di attivita', normalizzate in [0, 1];
- ``relative_event``: inizi e fini rispetto all'inizio del proprio caso (RED);
- ``absolute_event``: inizi e fini rispetto alla prima ora dei due log (AED);
- ``circadian_event``: ora del giorno di inizi e fini, giorno per giorno (CED);
- ``case_arrival``: arrivo dei casi rispetto alla prima ora dei due log (CAR).
"""

from __future__ import annotations

import csv
import gzip
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

METRICS = ("cycle_time_w1", "ngram", "relative_event", "absolute_event", "circadian_event", "case_arrival")

_HOUR = 3600.0
# Il massimo scarto fra due ore del giorno: la penalita' di un giorno della
# settimana che ha eventi in un log solo.
_MAX_HOUR_GAP = 23.0

# scipy.stats.t.ppf(0.975, df) per df = 1..30, come compute_mean_conf_interval del paper.
_T_975 = (
    12.706204736174694, 4.302652729749462, 3.1824463052837078, 2.7764451051977934, 2.5705818356363146,
    2.4469118511449786, 2.364624251592784, 2.306004135204166, 2.262157162798205, 2.228138851986274,
    2.200985160091639, 2.1788128296672284, 2.1603686564627913, 2.144786687917804, 2.131449545559776,
    2.1199052992212546, 2.1098155778333156, 2.1009220402410382, 2.0930240544083087, 2.085963447265864,
    2.0796138447276795, 2.0738730679040254, 2.0686576104190486, 2.0638985616280245, 2.0595385527532972,
    2.0555294386428735, 2.0518305164802846, 2.0484071417952454, 2.045229642132703, 2.0422724563012378,
)


@dataclass(frozen=True, slots=True)
class Event:
    case_id: str
    activity: str
    start: datetime
    end: datetime


def parse_instant(raw: str) -> datetime:
    """Un istante ISO 8601 in UTC; senza fuso e' gia' UTC, come in ``read_csv_log`` di pix."""
    instant = datetime.fromisoformat(raw)
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def read_csv_log(path: Path) -> list[Event]:
    """Un event log CSV (anche ``.gz``) con ``case_id``, ``activity``, ``start_time``, ``end_time``."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        return events_from_rows(csv.DictReader(handle))


def events_from_rows(rows: Iterable[dict[str, str]]) -> list[Event]:
    return [
        Event(row["case_id"], row["activity"], parse_instant(row["start_time"]), parse_instant(row["end_time"]))
        for row in rows
    ]


def wasserstein_1d(u: Sequence[int], v: Sequence[int]) -> float:
    """Wasserstein-1 fra due campioni di bin interi: l'area fra le due CDF a gradini.

    La stessa formula di ``scipy.stats.wasserstein_distance`` senza pesi, ma in
    aritmetica intera fino alla divisione finale: il risultato non dipende
    dall'ordine dei campioni.
    """
    if not u or not v:
        raise ValueError("Servono due campioni non vuoti.")
    count_u, count_v = Counter(u), Counter(v)
    values = sorted(count_u.keys() | count_v.keys())
    n_u, n_v = len(u), len(v)
    seen_u = seen_v = area = 0
    for value, following in pairwise(values):
        seen_u += count_u[value]
        seen_v += count_v[value]
        area += abs(seen_u * n_v - seen_v * n_u) * (following - value)
    return area / (n_u * n_v)


def _cases(log: Iterable[Event]) -> dict[str, list[Event]]:
    cases: dict[str, list[Event]] = {}
    for event in log:
        cases.setdefault(event.case_id, []).append(event)
    return cases


def _hour_bin(seconds: float) -> int:
    return math.floor(seconds / _HOUR)


def _floor_hour(instant: datetime) -> datetime:
    return instant.replace(minute=0, second=0, microsecond=0)


def cycle_time_w1(original: Sequence[Event], simulated: Sequence[Event]) -> float:
    """``cycle_time_distribution_distance`` con bin di un'ora, come SIMOD."""
    durations = [
        [max(e.end for e in events) - min(e.start for e in events) for events in _cases(log).values()]
        for log in (original, simulated)
    ]
    shortest = min(min(durations[0]), min(durations[1]))
    bins = [[math.floor((d - shortest).total_seconds() / _HOUR) for d in side] for side in durations]
    return wasserstein_1d(bins[0], bins[1])


def _ngrams(log: Sequence[Event], n: int) -> Counter[tuple[str | None, ...]]:
    grams: Counter[tuple[str | None, ...]] = Counter()
    padding: list[str | None] = [None] * (n - 1)
    for events in _cases(log).values():
        # Ordinamento stabile per (inizio, fine), come sort_values di pandas su due colonne.
        trace = padding + [e.activity for e in sorted(events, key=lambda e: (e.start, e.end))] + padding
        grams.update(tuple(trace[i : i + n]) for i in range(len(trace) - n + 1))
    return grams


def ngram_distance(original: Sequence[Event], simulated: Sequence[Event], n: int = 3) -> float:
    """``n_gram_distribution_distance`` normalizzata: 0 stessi n-grammi, 1 nessuno in comune."""
    a, b = _ngrams(original, n), _ngrams(simulated, n)
    total = sum(a.values()) + sum(b.values())
    return sum(abs(a[key] - b[key]) for key in a.keys() | b.keys()) / total


def _relative_bins(log: Sequence[Event]) -> list[int]:
    starts: list[int] = []
    ends: list[int] = []
    for events in _cases(log).values():
        case_start = min(e.start for e in events)
        starts += [_hour_bin((e.start - case_start).total_seconds()) for e in events]
        ends += [_hour_bin((e.end - case_start).total_seconds()) for e in events]
    return starts + ends


def relative_event_distance(original: Sequence[Event], simulated: Sequence[Event]) -> float:
    """``relative_event_distribution_distance`` (RED): inizi e fini rispetto all'inizio del caso."""
    return wasserstein_1d(_relative_bins(original), _relative_bins(simulated))


def absolute_event_distance(original: Sequence[Event], simulated: Sequence[Event]) -> float:
    """``absolute_event_distribution_distance`` (AED): inizi e fini dalla prima ora dei due log."""
    origin = _floor_hour(min(min(e.start for e in original), min(e.start for e in simulated)))

    def bins(log: Sequence[Event]) -> list[int]:
        return [_hour_bin((e.start - origin).total_seconds()) for e in log] + [
            _hour_bin((e.end - origin).total_seconds()) for e in log
        ]

    return wasserstein_1d(bins(original), bins(simulated))


def circadian_event_distance(original: Sequence[Event], simulated: Sequence[Event]) -> float:
    """``circadian_event_distribution_distance`` (CED): ore del giorno, giorno della settimana per giorno."""

    def by_weekday(log: Sequence[Event]) -> dict[int, list[int]]:
        days: dict[int, list[int]] = {}
        for instant in [e.start for e in log] + [e.end for e in log]:
            days.setdefault(instant.weekday(), []).append(instant.hour)
        return days

    a, b = by_weekday(original), by_weekday(simulated)
    distances: list[float] = []
    for day in range(7):
        if day in a and day in b:
            distances.append(wasserstein_1d(a[day], b[day]))
        elif day in a or day in b:
            distances.append(_MAX_HOUR_GAP)
        else:
            distances.append(0.0)
    return mean(distances)


def case_arrival_distance(original: Sequence[Event], simulated: Sequence[Event]) -> float:
    """``case_arrival_distribution_distance`` (CAR): arrivo dei casi dalla prima ora dei due log."""
    arrivals = [[min(e.start for e in events) for events in _cases(log).values()] for log in (original, simulated)]
    origin = _floor_hour(min(min(arrivals[0]), min(arrivals[1])))
    bins = [[_hour_bin((a - origin).total_seconds()) for a in side] for side in arrivals]
    return wasserstein_1d(bins[0], bins[1])


def distances(original: Sequence[Event], simulated: Sequence[Event]) -> dict[str, float]:
    """Le sei distanze di B2, ``original`` e' il log reale (o di riferimento)."""
    if not original or not simulated:
        raise ValueError("Il log di riferimento e quello simulato devono avere eventi.")
    return {
        "cycle_time_w1": cycle_time_w1(original, simulated),
        "ngram": ngram_distance(original, simulated),
        "relative_event": relative_event_distance(original, simulated),
        "absolute_event": absolute_event_distance(original, simulated),
        "circadian_event": circadian_event_distance(original, simulated),
        "case_arrival": case_arrival_distance(original, simulated),
    }


def mean_confidence_interval(values: Sequence[float]) -> tuple[float, float]:
    """Media e semiampiezza dell'intervallo t di Student al 95%, come il paper."""
    n = len(values)
    if not 2 <= n <= len(_T_975) + 1:
        raise ValueError(f"Servono da 2 a {len(_T_975) + 1} repliche, non {n}.")
    average = math.fsum(values) / n
    std = math.sqrt(math.fsum((v - average) ** 2 for v in values) / (n - 1))
    return average, _T_975[n - 2] * std / math.sqrt(n)
