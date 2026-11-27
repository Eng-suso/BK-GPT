"""KPI di un event log canonico con lo stesso calcolo del log simulato.

Il riassunto viene da ``log_processor`` (la stessa funzione che legge i run di
Prosimos), cosi' "cycle time" vuol dire la stessa cosa sui due lati del
confronto. Cio' che un log reale non sa non diventa zero:

- **abilitazione**: un log reale registra inizio e fine, non quando l'attivita'
  e' diventata eseguibile (a meno che la colonna sia mappata, come nei log
  simulati esportati). Altrimenti si usa la fine dell'evento precedente dello stesso
  caso (convenzione del process mining); il primo evento parte dal suo inizio;
- **inizio mancante**: con solo il completamento l'attesa non si separa dalla
  lavorazione; l'evento parte dall'abilitazione e tutto il tempo e' lavorazione.
  ``timing`` lo dichiara;
- **utilizzo**: senza calendari di disponibilita' non si misura: assente;
- **costo**: somma dei costi degli eventi se la colonna e' mappata, altrimenti assente;
- **cause delle attese** (``waitingCauses``, B3.2): solo se inizio e risorsa ci sono su almeno
  il 95% degli eventi; altrimenti assenti (``None``), non zero.
"""

from __future__ import annotations

from typing import Literal

from backend.eventlog.model import CanonicalEvent, EventLog
from backend.eventlog.waiting import MIN_OBSERVED, executions_of, waiting_by_activity
from backend.simulation.engine import LogEvent, get_engine

Timing = Literal["start_and_end", "complete_only", "mixed"]


def to_log_events(log: EventLog) -> list[LogEvent]:
    """Gli eventi nella forma del calcolatore dei KPI, con l'abilitazione ricavata."""
    events: list[LogEvent] = []
    for case_events in log.cases().values():
        previous_end: float | None = None
        for event in case_events:
            end = event.end.timestamp()
            start = event.start.timestamp() if event.start else None
            if event.enabled is not None:
                enable = event.enabled.timestamp()
            else:
                enable = previous_end if previous_end is not None else (start if start is not None else end)
            if start is not None:
                enable = min(enable, start)
            events.append(LogEvent(
                case_id=event.case_id,
                activity=event.activity,
                enable=enable,
                start=start if start is not None else enable,
                end=end,
                resource=event.resource or "",
            ))
            previous_end = end if previous_end is None else max(previous_end, end)
    return events


def timing(log: EventLog) -> Timing:
    with_start = sum(1 for event in log.events if event.start is not None)
    if with_start == len(log.events):
        return "start_and_end"
    return "complete_only" if with_start == 0 else "mixed"


def summarize(log: EventLog, name_to_element_id: dict[str, str] | None = None, *, with_waiting_causes: bool = True) -> dict:
    """I KPI del log, con ``timing`` e ``source`` per dire su cosa si basano.

    ``with_waiting_causes=False`` salta le cause delle attese (chi non le legge non le paga).
    """
    if not log.events:
        raise ValueError("Il log non contiene eventi validi: niente da misurare.")
    summary = get_engine().summarize_events(to_log_events(log), name_to_element_id=name_to_element_id or {})
    summary["cost"] = _cost(log.events, len({e.case_id for e in log.events}))
    summary["byResource"] = []
    summary["timing"] = timing(log)
    summary["firstEnableObserved"] = all(events[0].enabled is not None for events in log.cases().values())
    summary["enablementObserved"] = all(event.enabled is not None for event in log.events)
    summary["source"] = log.origin
    if with_waiting_causes:
        summary["waitingCauses"] = waiting_causes(log, name_to_element_id or {})
    return summary


def waiting_causes(log: EventLog, name_to_element_id: dict[str, str]) -> dict | None:
    """Le cause delle attese per attivita' (secondi totali), o None se il log non le fa vedere."""
    executions, observed = executions_of((e.case_id, e.activity, e.start, e.end, e.resource, e.enabled) for e in log.events)
    if observed < MIN_OBSERVED:
        return None
    return {
        "activities": [
            {"name": row.activity, "el": name_to_element_id.get(row.activity), "executions": row.executions,
             "waiting": row.waiting, "seconds": {cause: round(value, 1) for cause, value in row.seconds.items()}}
            for row in waiting_by_activity(executions)
        ],
    }


def _cost(events: tuple[CanonicalEvent, ...], cases: int) -> dict | None:
    costs = [event.cost for event in events if event.cost is not None]
    if not costs:
        return None
    total = sum(costs)
    return {"total": total, "perCase": total / cases if cases else None, "eventsWithCost": len(costs)}
