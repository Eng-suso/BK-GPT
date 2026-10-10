"""L'obiettivo di servizio (SLA) di uno scenario e il suo esito sul run (SIM-13).

Il consulente dice "il caso si chiude entro X per almeno il Y% dei casi". Il
motore non lo conosce: e' una misura sul log, con la stessa definizione di
cycle time dei KPI (ultima fine - prima abilitazione del caso).
"""

from __future__ import annotations

from backend.simulation.log_processor import parse_prosimos_log


def sla_outcome(log_csv: str, *, target_seconds: float, share: float) -> dict | None:
    """Quanti casi completati stanno nel target, e se l'obiettivo e' rispettato.

    ``None`` se il log non ha casi: senza casi non c'e' niente da giudicare.
    """
    first_enable: dict[str, float] = {}
    last_end: dict[str, float] = {}
    for event in parse_prosimos_log(log_csv):
        first_enable[event.case_id] = min(first_enable.get(event.case_id, event.enable), event.enable)
        last_end[event.case_id] = max(last_end.get(event.case_id, event.end), event.end)
    cases = len(last_end)
    if cases == 0:
        return None
    within = sum(1 for case_id, end in last_end.items() if end - first_enable[case_id] <= target_seconds)
    share_within = within / cases
    return {
        "target_seconds": target_seconds,
        "share_target": share,
        "share_within": round(share_within, 4),
        "cases": cases,
        "late_cases": cases - within,
        "met": share_within >= share,
    }
