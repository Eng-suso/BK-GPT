"""Arrivi con un ritmo diverso per fascia oraria (SIM-08), generati dal runner.

Prosimos 2.1 ha una sola distribuzione degli arrivi e un calendario che dice
solo *quando* possono arrivare casi, non *quanti*: un picco dalle 9 alle 12 non
si esprime. Accetta pero' gli istanti di arrivo gia' calcolati
(``run_simulation(..., fixed_arrival_times=...)``). Il runner li calcola qui
quando lo scenario porta la sezione DeliR ``delir_arrival_bands``.

Ogni fascia ha il suo tempo medio fra due arrivi: dentro la fascia gli arrivi
sono un processo di Poisson con quel ritmo, fuori da ogni fascia non arriva
nessuno. Il processo a tratti si genera esatto: si estrae un "lavoro" Exp(1) e
lo si consuma attraversando le fasce, ognuna al suo ritmo, cosi' un intervallo
che scavalca la fine di una fascia continua nella successiva senza perdere la
memoryless property.

I numeri casuali vengono da ``numpy.random``, inizializzato dal runner con il
seed del run: stesso seed, stessi arrivi.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy

SECTION = "delir_arrival_bands"
# SIM-33: il nome di un attributo del caso che riceve la fascia in cui il caso
# e' arrivato ("Fascia 1", "Fascia 2", ... nell'ordine delle fasce). Durate per
# categoria e decisioni per regola lo leggono come qualsiasi altro attributo.
ATTRIBUTE_SECTION = "delir_arrival_band_attribute"
_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_WEEK = 7 * 86_400


def band_label(index: int) -> str:
    """Il valore dell'attributo per la fascia ``index`` (da 0), lo stesso che scrive il backend."""
    return f"Fascia {index + 1}"


def weekly_intervals(bands: list[dict]) -> list[tuple[float, float, float]]:
    """Le fasce come intervalli della settimana: (inizio, fine, arrivi al secondo), da lunedi' 00:00."""
    return [(begin, end, rate) for begin, end, rate, _ in _band_intervals(bands)]


def _band_intervals(bands: list[dict]) -> list[tuple[float, float, float, int]]:
    """Come ``weekly_intervals``, con l'indice della fascia da cui viene ogni intervallo."""
    intervals = []
    for index, band in enumerate(bands):
        first, last = _DAYS.index(band["from"]), _DAYS.index(band["to"])
        begin, end = _seconds(band["beginTime"]), _seconds(band["endTime"])
        mean = float(band["meanSeconds"])
        if mean <= 0 or begin >= end:
            raise ValueError(f"fascia non valida: {band}")
        days = range(first, last + 1) if first <= last else [*range(first, 7), *range(0, last + 1)]
        intervals.extend((day * 86_400 + begin, day * 86_400 + end, 1.0 / mean, index) for day in days)
    intervals.sort()
    for (_, end, _, _), (begin, _, _, _) in zip(intervals, intervals[1:]):
        if begin < end:
            raise ValueError("due fasce degli arrivi si sovrappongono")
    if not intervals:
        raise ValueError("nessuna fascia degli arrivi")
    return intervals


def arrival_offsets(bands: list[dict], start: datetime, count: int) -> list[float]:
    """I secondi dall'inizio del run a cui arrivano i primi ``count`` casi."""
    return arrival_plan(bands, start, count)[0]


def arrival_plan(bands: list[dict], start: datetime, count: int) -> tuple[list[float], list[int]]:
    """Gli arrivi dei primi ``count`` casi e, per ognuno, l'indice della fascia in cui arriva."""
    intervals = _band_intervals(bands)
    monday = start - timedelta(days=start.weekday(), hours=start.hour, minutes=start.minute,
                               seconds=start.second, microseconds=start.microsecond)
    origin = (start - monday).total_seconds()
    position = origin
    need = float(numpy.random.exponential(1.0))
    offsets: list[float] = []
    indices: list[int] = []
    week = 0
    while True:
        for begin, end, rate, index in intervals:
            low, high = max(begin + week * _WEEK, position), end + week * _WEEK
            if low >= high:
                continue
            while need <= (high - low) * rate:
                low += need / rate
                offsets.append(low - origin)
                indices.append(index)
                if len(offsets) == count:
                    return offsets, indices
                need = float(numpy.random.exponential(1.0))
            need -= (high - low) * rate
            position = high
        week += 1


def _seconds(clock: str) -> float:
    hours, minutes, seconds = clock.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
