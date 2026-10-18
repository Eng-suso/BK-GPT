"""SIM-25: le varianti di uno scenario per il tornado di sensitivita'.

Ogni ipotesi incerta si sposta di -delta e +delta, una alla volta, tenendo
ferme le altre. La variante e' la stessa richiesta del pannello con un solo
numero cambiato, cosi' passa dalla stessa traduzione verso il motore.

- Durata di un'attivita': si scalano media, deviazione e limiti, anche degli
  altri ruoli e delle durate per categoria, cosi' la forma resta quella.
- Arrivi: si scala il tempo fra due arrivi (anche per fascia oraria). -20%
  vuol dire arrivi piu' fitti.
- Decisione: si scala la probabilita' del ramo piu' probabile e gli altri si
  ridistribuiscono il resto in proporzione, cosi' la somma resta 1.
"""

from __future__ import annotations

from typing import Literal

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    SensitivityFactor,
    SimGatewayConfig,
    SimTaskConfig,
)

Direction = Literal["low", "high"]


def factor_scale(direction: Direction, delta: float) -> float:
    return 1 - delta if direction == "low" else 1 + delta


def perturb(
    request: CreateSimulationRunRequest,
    factor: SensitivityFactor,
    direction: Direction,
    delta: float,
) -> CreateSimulationRunRequest:
    """La richiesta con la sola ipotesi ``factor`` spostata nel verso ``direction``."""
    scale = factor_scale(direction, delta)
    if factor.kind == "arrival":
        return _scaled_arrivals(request, scale)
    if factor.kind == "duration":
        return _scaled_duration(request, factor, scale)
    return _shifted_gateway(request, factor, scale)


def _times(value: float | None, scale: float) -> float | None:
    return None if value is None else value * scale


def _scaled_arrivals(request: CreateSimulationRunRequest, scale: float) -> CreateSimulationRunRequest:
    if request.arrival is None:
        return request.model_copy(update={
            "arrival_interval_seconds": max(1, round(request.arrival_interval_seconds * scale)),
        })
    arrival = request.arrival
    scaled = arrival.model_copy(update={
        "mean_seconds": arrival.mean_seconds * scale,
        "std_seconds": _times(arrival.std_seconds, scale),
        "min_seconds": _times(arrival.min_seconds, scale),
        "max_seconds": _times(arrival.max_seconds, scale),
        "bands": [band.model_copy(update={"mean_seconds": band.mean_seconds * scale}) for band in arrival.bands],
    })
    return request.model_copy(update={"arrival": scaled})


def _scaled_task(task: SimTaskConfig, scale: float) -> SimTaskConfig:
    def durations(item):
        return item.model_copy(update={
            "mean_seconds": item.mean_seconds * scale,
            "std_seconds": _times(item.std_seconds, scale),
            "min_seconds": _times(item.min_seconds, scale),
            "max_seconds": _times(item.max_seconds, scale),
        })

    scaled = durations(task)
    update: dict = {"other_assignments": [durations(other) for other in task.other_assignments]}
    if task.duration_by is not None:
        update["duration_by"] = task.duration_by.model_copy(update={
            "variants": [durations(variant) for variant in task.duration_by.variants],
        })
    return scaled.model_copy(update=update)


def _scaled_duration(
    request: CreateSimulationRunRequest,
    factor: SensitivityFactor,
    scale: float,
) -> CreateSimulationRunRequest:
    tasks = request.tasks or []
    if not any(task.element_id == factor.element_id for task in tasks):
        raise ValueError(f"L'attivita' {factor.label or factor.element_id} non ha una durata nello scenario.")
    return request.model_copy(update={
        "tasks": [_scaled_task(task, scale) if task.element_id == factor.element_id else task for task in tasks],
    })


def _shifted_branches(gateway: SimGatewayConfig, scale: float) -> SimGatewayConfig:
    branches = gateway.branches
    main = max(range(len(branches)), key=lambda i: branches[i].probability)
    p = min(1.0, max(0.0, branches[main].probability * scale))
    rest = sum(b.probability for i, b in enumerate(branches) if i != main)
    others = len(branches) - 1

    def share(i: int) -> float:
        if i == main:
            return p
        # Rami a zero restano a zero; se tutti gli altri sono a zero il resto si divide in parti uguali.
        return branches[i].probability * (1 - p) / rest if rest > 0 else (1 - p) / others

    return gateway.model_copy(update={
        "branches": [b.model_copy(update={"probability": share(i)}) for i, b in enumerate(branches)],
    })


def _shifted_gateway(
    request: CreateSimulationRunRequest,
    factor: SensitivityFactor,
    scale: float,
) -> CreateSimulationRunRequest:
    gateways = request.gateways or []
    target = next((g for g in gateways if g.element_id == factor.element_id), None)
    if target is None or len(target.branches) < 2:
        raise ValueError(f"La decisione {factor.label or factor.element_id} non ha rami da far variare nello scenario.")
    return request.model_copy(update={
        "gateways": [_shifted_branches(g, scale) if g.element_id == factor.element_id else g for g in gateways],
    })
