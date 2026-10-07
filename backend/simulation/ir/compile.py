"""Dal Simulation IR allo scenario JSON di Prosimos.

Il contratto di riferimento e' Prosimos 2.1.0 (spike G1). Le sezioni che la
1.2.6 non esegue - ``branch_rules``, ``event_attributes`` - compaiono solo se il
modello le usa: un modello senza regole produce lo stesso JSON che DeliR
mandava prima dell'IR, e gira su entrambi i motori.

Formati del motore che qui si rispettano (pix-framework):
- ``fix``: [valore]; ``expon``: [media, minimo, massimo];
- ``uniform``: [minimo, massimo]; ``norm``: [media, dev. std, minimo, massimo];
- ``lognorm`` e ``gamma``: [media, varianza, minimo, massimo];
- costo orario e probabilita' come stringhe, come le scriveva il builder.
"""

from __future__ import annotations

from backend.simulation.ir.model import (
    Calendar,
    CalendarPeriod,
    Condition,
    Exponential,
    Fixed,
    Gamma,
    LogNormal,
    Normal,
    SimulationModel,
    Uniform,
)


def compile_for_prosimos(model: SimulationModel) -> dict:
    """Lo scenario Prosimos che esegue ``model``."""
    calendars = {calendar.id: calendar for calendar in model.calendars}
    assigned: dict[str, list[str]] = {}
    for activity in model.activities:
        for assignment in activity.assignments:
            assigned.setdefault(assignment.resource_id, []).append(activity.element_id)

    payload: dict = {
        "resource_profiles": [
            {
                "id": pool.id,
                "name": pool.name,
                "resource_list": [
                    {
                        "id": resource.id,
                        "name": resource.name,
                        "cost_per_hour": str(float(resource.cost_per_hour)),
                        "amount": int(resource.amount),
                        "calendar": resource.calendar_id,
                        "assignedTasks": assigned.get(resource.id, []),
                    }
                    for resource in pool.resources
                ],
            }
            for pool in model.pools
        ],
        "arrival_time_distribution": distribution_params(model.arrival.interarrival),
        "arrival_time_calendar": [_period(p) for p in calendars[model.arrival.calendar_id].periods],
        "gateway_branching_probabilities": [
            {
                "gateway_id": gateway.element_id,
                "probabilities": [
                    {
                        "path_id": branch.flow_id,
                        "value": str(branch.probability),
                        **({"condition_id": _rule_id(gateway.element_id, branch.flow_id)} if branch.condition else {}),
                    }
                    for branch in gateway.branches
                ],
            }
            for gateway in model.gateways
        ],
        "task_resource_distribution": [
            {
                "task_id": activity.element_id,
                "resources": [
                    {"resource_id": assignment.resource_id, **distribution_params(assignment.duration)}
                    for assignment in activity.assignments
                ],
            }
            for activity in model.activities
        ],
        "resource_calendars": [_calendar(calendar) for calendar in _used_resource_calendars(model, calendars)],
        "batch_processing": [],
        "case_attributes": [_case_attribute(attribute) for attribute in model.case_attributes],
    }

    branch_rules = [
        {"id": _rule_id(gateway.element_id, branch.flow_id), "rules": _rules(branch.condition)}
        for gateway in model.gateways
        for branch in gateway.branches
        if branch.condition is not None
    ]
    if branch_rules:
        payload["branch_rules"] = branch_rules

    if model.attribute_updates:
        by_element: dict[str, list[dict]] = {}
        for update in model.attribute_updates:
            by_element.setdefault(update.element_id, []).append(
                {"name": update.name, "type": "expression", "values": update.expression}
            )
        payload["event_attributes"] = [
            {"event_id": element_id, "attributes": attributes}
            for element_id, attributes in by_element.items()
        ]

    if model.priority_rules:
        payload["prioritisation_rules"] = [
            {"priority_level": rule.level, "rules": _rules(rule.condition)}
            for rule in sorted(model.priority_rules, key=lambda r: r.level)
        ]
    return payload


def distribution_params(distribution) -> dict:
    """Una distribuzione dell'IR nel formato ``distribution_name``/``distribution_params``."""
    if isinstance(distribution, Fixed):
        name, values = "fix", [distribution.value]
    elif isinstance(distribution, Exponential):
        name, values = "expon", [distribution.mean, distribution.minimum, distribution.maximum]
    elif isinstance(distribution, Uniform):
        name, values = "uniform", [distribution.minimum, distribution.maximum]
    elif isinstance(distribution, Normal):
        name, values = "norm", [distribution.mean, distribution.std, distribution.minimum, distribution.maximum]
    elif isinstance(distribution, LogNormal):
        name, values = "lognorm", [distribution.mean, distribution.variance, distribution.minimum, distribution.maximum]
    elif isinstance(distribution, Gamma):
        name, values = "gamma", [distribution.mean, distribution.variance, distribution.minimum, distribution.maximum]
    else:  # pragma: no cover - l'unione discriminata non ne ammette altre
        raise TypeError(f"distribuzione non compilabile: {distribution!r}")
    return {"distribution_name": name, "distribution_params": [{"value": float(v)} for v in values]}


def _used_resource_calendars(model: SimulationModel, calendars: dict[str, Calendar]) -> list[Calendar]:
    # Solo i calendari che una risorsa usa, nell'ordine in cui compaiono: quello
    # degli arrivi va nella sua sezione, non fra le risorse.
    used: list[str] = []
    for resource in model.resources().values():
        if resource.calendar_id not in used:
            used.append(resource.calendar_id)
    return [calendars[calendar_id] for calendar_id in used]


def _calendar(calendar: Calendar) -> dict:
    return {
        "id": calendar.id,
        "name": calendar.name,
        "time_periods": [_period(period) for period in calendar.periods],
    }


def _period(period: CalendarPeriod) -> dict:
    return {
        "from": period.from_day,
        "to": period.to_day,
        "beginTime": period.begin,
        "endTime": period.end,
    }


def _case_attribute(attribute) -> dict:
    if attribute.options is not None:
        return {
            "name": attribute.name,
            "type": "discrete",
            "values": [{"key": option.value, "value": option.probability} for option in attribute.options],
        }
    return {"name": attribute.name, "type": "continuous", "values": distribution_params(attribute.distribution)}


def _rules(condition: Condition) -> list[list[dict]]:
    return [
        [{"attribute": rule.attribute, "comparison": rule.operator, "value": _rule_value(rule.value)} for rule in group]
        for group in condition.any_of
    ]


def _rule_value(value: str | float) -> str:
    # Il motore confronta come numero quando puo'; "5000" si legge meglio di "5000.0".
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _rule_id(gateway_id: str, flow_id: str) -> str:
    return f"{gateway_id}::{flow_id}"
