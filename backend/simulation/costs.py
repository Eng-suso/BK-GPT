"""I costi fissi di uno scenario, sommati al costo delle risorse (SIM-10).

Prosimos paga solo il tempo di lavoro delle risorse a tariffa oraria. Il
consulente puo' aggiungere un costo fisso per esecuzione di un'attivita' (una
pratica, una spedizione) e un costo fisso per caso: si sommano qui, sul run
completato, con il dettaglio di cosa viene da dove.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FixedCosts:
    # element_id -> euro per esecuzione dell'attivita'
    per_execution: dict[str, float] = field(default_factory=dict)
    # euro per ogni caso completato
    per_case: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.per_execution) or self.per_case > 0


def add_fixed_costs(summary: dict, costs: FixedCosts) -> dict:
    """Il riepilogo con i costi fissi nel totale e il dettaglio in ``cost``.

    Ogni riga di ``byActivity`` con un costo per esecuzione riceve ``fixedCost``
    (esecuzioni x costo). Il riepilogo arriva gia' calcolato: qui si somma, non si
    ricalcola il costo delle risorse.
    """
    cost = summary.get("cost") or {}
    resources = float(cost.get("total") or 0.0)
    activities = 0.0
    for row in summary.get("byActivity") or []:
        unit = costs.per_execution.get(row.get("el") or "")
        if unit:
            row["fixedCost"] = round(unit * int(row.get("count") or 0), 2)
            activities += row["fixedCost"]
    cases = int(summary.get("casesCompleted") or 0)
    per_case = round(costs.per_case * cases, 2)
    total = resources + activities + per_case
    summary["cost"] = {
        **cost,
        "total": total,
        "perCase": total / cases if cases else 0.0,
        "breakdown": {"resources": resources, "activities": activities, "cases": per_case},
    }
    return summary
