"""Confronto fra uno scenario Prosimos originale e quello che DeliR compila dopo l'import.

Usato dal test di fedeltà e dall'harness di valutazione: se l'import cambia
cosa si simula, i numeri del benchmark non misurano piu' lo scenario di partenza.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

PARAM_REL_TOL = 1e-3
#: Le durate passano dai minuti della bozza ai secondi: mezzo secondo di arrotondamento.
PARAM_ABS_TOL = 0.51
PROBABILITY_TOL = 0.006


def _params(distribution: dict[str, Any]) -> list[float]:
    return [float(p["value"]) for p in distribution["distribution_params"]]


def _name(name: str) -> str:
    return "fix" if name == "fixed" else name


def _close(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(
        math.isclose(x, y, rel_tol=PARAM_REL_TOL, abs_tol=PARAM_ABS_TOL) for x, y in zip(a, b, strict=True)
    )


def _same_distribution(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _name(a["distribution_name"]) == _name(b["distribution_name"]) and _close(_params(a), _params(b))


def differences(original: dict[str, Any], compiled: dict[str, Any]) -> Counter[str]:
    """Che cosa simula diversamente lo scenario compilato; vuoto = fedele."""
    issues: Counter[str] = Counter()
    durations = {
        t["task_id"]: {r["resource_id"]: r for r in t["resources"]} for t in compiled["task_resource_distribution"]
    }
    for task in original["task_resource_distribution"]:
        for resource in task["resources"]:
            got = durations.get(task["task_id"], {}).get(resource["resource_id"])
            if got is None:
                issues["durata assente"] += 1
            elif not _same_distribution(resource, got):
                issues[f"durata {_name(resource['distribution_name'])}"] += 1

    if not _same_distribution(original["arrival_time_distribution"], compiled["arrival_time_distribution"]):
        issues["arrivi"] += 1

    gateways = {
        g["gateway_id"]: {p["path_id"]: float(p["value"]) for p in g["probabilities"]}
        for g in compiled["gateway_branching_probabilities"]
    }
    for gateway in original["gateway_branching_probabilities"]:
        expected = {p["path_id"]: float(p["value"]) for p in gateway["probabilities"]}
        got = gateways.get(gateway["gateway_id"])
        if got is None:
            if len(expected) > 1:
                issues["decisione assente"] += 1
        elif any(abs(share - got.get(path, -1.0)) > PROBABILITY_TOL for path, share in expected.items()):
            issues["probabilita'"] += 1

    resources = {r["id"]: r for p in compiled["resource_profiles"] for r in p["resource_list"]}
    calendars = {c["id"]: c["time_periods"] for c in compiled["resource_calendars"]}
    original_calendars = {c["id"]: c["time_periods"] for c in original["resource_calendars"]}
    for profile in original["resource_profiles"]:
        for resource in profile["resource_list"]:
            got = resources.get(resource["id"])
            if got is None:
                issues["risorsa assente"] += 1
                continue
            if int(float(got["amount"])) != int(float(resource["amount"])):
                issues["quantita' risorsa"] += 1
            if not math.isclose(float(got["cost_per_hour"]), float(resource["cost_per_hour"]), abs_tol=0.01):
                issues["costo risorsa"] += 1
            want, have = original_calendars.get(resource.get("calendar")), calendars.get(got.get("calendar"))
            if want is not None and have is not None and len(want) != len(have):
                issues["calendario risorsa"] += 1

    events = {e["event_id"]: e for e in compiled.get("event_distribution", [])}
    for event in original.get("event_distribution", []):
        got = events.get(event["event_id"])
        if got is None:
            issues["attesa assente"] += 1
        elif not _same_distribution(event, got):
            issues["attesa"] += 1
    return issues
