"""Durate che cambiano con l'ora in cui l'attivita' inizia (SIM-33b), applicate dal runner.

"Dopo le 16 una pratica richiede il 30% in piu'", "il sabato mattina c'e' un
solo turno e si lavora piu' piano": la durata dipende da *quando* si lavora,
non da chi lavora ne' dal caso. Prosimos 2.1 non lo sa fare: campiona la
durata in ``TaskEvent.__init__`` dalla distribuzione della risorsa, senza
guardare l'ora, e nessuna sezione dello scenario lo cambia.

Il runner avvolge quel costruttore. Prosimos fa tutto come sempre; poi, se
l'attivita' e' iniziata dentro una fascia della sezione DeliR
``delir_duration_windows``, la durata ideale si moltiplica per il fattore della
fascia e quella reale si ricalcola con il calendario della risorsa, come fa
Prosimos (``SimDiffSetup.real_task_duration``), e con lei fine, attese e tempi
di lavorazione. Conta l'inizio: un'attivita' iniziata alle 15:55 non cambia
ritmo alle 16. Il numero casuale e' lo stesso del campione originale, quindi
stesso seed, stesso run.

La patch tocca un dettaglio interno di Prosimos: vale per la versione provata
(``SUPPORTED``). Con un'altra, uno scenario con la sezione si rifiuta invece di
simulare durate che nessuno ha applicato.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from importlib.metadata import version
from typing import Iterator

SECTION = "delir_duration_windows"
SUPPORTED = "2.1.0"
_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_MAX_FACTOR = 10.0

Intervals = list[tuple[float, float, float]]

# Le fasce del run in corso, per attivita'. Un worker sync serve un run alla
# volta (come per il seed, vedi runner.py): basta uno stato di modulo.
_active: dict[str, Intervals] = {}
_installed = False


def parse_windows(raw: object) -> dict[str, Intervals]:
    """La sezione come intervalli della settimana per attivita': (inizio, fine, fattore), da lunedi' 00:00."""
    if not isinstance(raw, dict) or not raw:
        raise ValueError("serve un oggetto attivita' -> fasce")
    out: dict[str, Intervals] = {}
    for task_id, windows in raw.items():
        if not isinstance(windows, list) or not windows:
            raise ValueError(f"{task_id}: serve almeno una fascia")
        intervals: Intervals = []
        for window in windows:
            first, last = _DAYS.index(window["from"]), _DAYS.index(window["to"])
            begin, end = _seconds(window["beginTime"]), _seconds(window["endTime"])
            factor = float(window["factor"])
            if not 0 < factor <= _MAX_FACTOR or begin >= end:
                raise ValueError(f"{task_id}: fascia non valida: {window}")
            days = range(first, last + 1) if first <= last else [*range(first, 7), *range(0, last + 1)]
            intervals.extend((day * 86_400 + begin, day * 86_400 + end, factor) for day in days)
        intervals.sort()
        for (_, end, _), (begin, _, _) in zip(intervals, intervals[1:]):
            if begin < end:
                raise ValueError(f"{task_id}: due fasce si sovrappongono")
        out[str(task_id)] = intervals
    return out


def factor_at(intervals: Intervals, moment: datetime) -> float:
    """Il fattore della fascia in cui cade ``moment``; fuori da ogni fascia, 1."""
    offset = (moment.weekday() * 86_400 + moment.hour * 3600 + moment.minute * 60
              + moment.second + moment.microsecond / 1e6)
    return next((factor for begin, end, factor in intervals if begin <= offset < end), 1.0)


def check_engine() -> None:
    """La patch e' scritta per ``SUPPORTED``: con un altro Prosimos le fasce non si applicano."""
    if version("prosimos") != SUPPORTED:
        raise ValueError(f"le durate per fascia oraria richiedono prosimos {SUPPORTED}, qui c'e' {version('prosimos')}")


@contextmanager
def applied(windows: dict[str, Intervals]) -> Iterator[None]:
    """Le fasce valgono per il run eseguito dentro il blocco, poi spariscono. Senza fasce, niente."""
    if not windows:
        yield
        return
    check_engine()
    _install()
    _active.clear()
    _active.update(windows)
    try:
        yield
    finally:
        _active.clear()


def _install() -> None:
    global _installed
    if _installed:
        return
    from prosimos.execution_info import TaskEvent

    original = TaskEvent.__init__

    def init(self, p_case, task_id, resource_id, resource_available_at=None, enabled_at=None,
             enabled_datetime=None, bpm_env=None, num_tasks_in_batch=0, batch_id=None):
        original(self, p_case, task_id, resource_id, resource_available_at, enabled_at,
                 enabled_datetime, bpm_env, num_tasks_in_batch, batch_id)
        intervals = _active.get(task_id)
        if resource_available_at is None or not intervals:
            return
        factor = factor_at(intervals, self.started_datetime)
        if factor != 1.0:
            _rescale(self, bpm_env, factor)

    TaskEvent.__init__ = init
    _installed = True


def _rescale(event, bpm_env, factor: float) -> None:
    """Gli stessi passi di ``TaskEvent.__init__`` (prosimos 2.1.0) dalla durata ideale in poi."""
    event.ideal_duration *= factor
    event.worked_intervals = []
    event.real_duration = bpm_env.sim_setup.real_task_duration(
        event.ideal_duration, event.resource_id, event.started_datetime, event.worked_intervals
    )
    event.completed_at = event.started_at + event.real_duration
    event.completed_datetime = bpm_env.simulation_datetime_from(event.completed_at)
    event.idle_time = event.real_duration - event.ideal_duration
    event.idle_cycle_time = event.completed_at - event.enabled_at
    event.idle_processing_time = event.completed_at - event.started_at
    event.cycle_time = event.idle_cycle_time - event.idle_time
    event.processing_time = event.idle_processing_time - event.idle_time


def _seconds(clock: str) -> float:
    hours, minutes, seconds = clock.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
