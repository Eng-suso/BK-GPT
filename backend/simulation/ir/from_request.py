"""Dalla richiesta di oggi (``CreateSimulationRunRequest``) al Simulation IR.

E' il ponte: la UI manda ancora medie, tre nomi di distribuzione e una risorsa
per attivita'; qui diventano un modello esplicito, con le stesse assunzioni del
builder storico rese visibili e marcate ``manual``. Il risultato compilato e'
identico allo scenario che il builder produceva (test di equivalenza).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CalendarPeriod,
    Exponential,
    Fixed,
    Gateway,
    Normal,
    Provenance,
    Resource,
    ResourcePool,
    SimulationModel,
)
from backend.simulation.models import BpmnGateway, BpmnTask

if TYPE_CHECKING:
    # Solo per i tipi: lo schema HTTP importa il modello dell'IR (richiesta v2),
    # e un import a runtime qui chiuderebbe il cerchio.
    from backend.schemas.simulation import CreateSimulationRunRequest

STANDARD_CALENDAR_ID = "delir-calendar-standard"
DEFAULT_RESOURCE_ID = "delir-resource-operator"
DEFAULT_POOL_ID = "delir-profile-operator"

# Quello che il consulente ha inserito nel pannello: provenienza `manual`.
_MANUAL = Provenance(origin="manual")


def standard_calendar() -> Calendar:
    return Calendar(
        id=STANDARD_CALENDAR_ID,
        name="Standard office calendar",
        periods=(CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00.000", end="17:00:00.000"),),
    )


def model_from_request(
    request: CreateSimulationRunRequest,
    tasks: list[BpmnTask],
    gateways: list[BpmnGateway],
) -> SimulationModel:
    """Il modello che la richiesta descrive, con i default storici dichiarati."""
    if not tasks:
        raise ValueError("Il BPMN non contiene task simulabili.")
    task_overrides = {cfg.element_id: cfg for cfg in (request.tasks or [])}
    pool = _pool(request, tasks, task_overrides)
    resource_ids = [resource.id for resource in pool.resources]
    default_resource_id = resource_ids[0]
    gateway_overrides = {cfg.element_id: cfg for cfg in (request.gateways or [])}

    arrival_mean = max(1.0, float(request.arrival_interval_seconds))
    return SimulationModel(
        arrival=Arrival(
            interarrival=Exponential(mean=arrival_mean, minimum=0.0, maximum=arrival_mean * 10.0),
            calendar_id=STANDARD_CALENDAR_ID,
            provenance=_MANUAL,
        ),
        calendars=(standard_calendar(),),
        pools=(pool,),
        activities=tuple(
            _activity(task, task_overrides.get(task.id), request, default_resource_id, set(resource_ids))
            for task in tasks
        ),
        gateways=tuple(_gateway(gateway, gateway_overrides.get(gateway.id)) for gateway in gateways),
    )


def duration_from_mean(distribution: str, mean: float):
    """Le assunzioni storiche: dev. std al 10% della media, limiti a +-3 sigma,
    esponenziale troncata a 10 volte la media."""
    mean = max(1.0, mean)
    if distribution == "fixed":
        return Fixed(value=mean)
    if distribution == "expon":
        return Exponential(mean=mean, minimum=0.0, maximum=mean * 10.0)
    std = max(1.0, mean * 0.1)
    return Normal(mean=mean, std=std, minimum=max(0.0, mean - 3.0 * std), maximum=mean + 3.0 * std)


def _pool(request: CreateSimulationRunRequest, tasks: list[BpmnTask], task_overrides: dict) -> ResourcePool:
    if request.resources is not None:
        if not request.resources:
            raise ValueError("Definisci almeno una risorsa per simulare il processo.")
        ids = [cfg.id for cfg in request.resources]
        if len(set(ids)) != len(ids):
            raise ValueError("Le risorse devono avere identificativi distinti.")
        if any(not cfg.name.strip() for cfg in request.resources):
            raise ValueError("Assegna un nome alle risorse.")
        if any(not task_overrides.get(t.id) or task_overrides[t.id].resource_id not in ids for t in tasks):
            raise ValueError("Assegna una risorsa valida a ogni attività prima di simulare.")
        return ResourcePool(
            id=DEFAULT_POOL_ID,
            name="Risorse",
            resources=tuple(
                Resource(
                    id=cfg.id,
                    name=cfg.name,
                    cost_per_hour=float(cfg.cost_per_hour),
                    amount=int(cfg.amount),
                    calendar_id=STANDARD_CALENDAR_ID,
                    provenance=_MANUAL,
                )
                for cfg in request.resources
            ),
        )
    name = request.resource_name.strip() or "Operatore"
    return ResourcePool(
        id=DEFAULT_POOL_ID,
        name=name,
        resources=(
            Resource(
                id=DEFAULT_RESOURCE_ID,
                name=name,
                cost_per_hour=float(request.default_cost_per_hour),
                amount=int(request.resource_amount),
                calendar_id=STANDARD_CALENDAR_ID,
                provenance=_MANUAL,
            ),
        ),
    )


def _activity(task: BpmnTask, override, request, default_resource_id: str, resource_ids: set[str]) -> Activity:
    mean = float(override.mean_seconds) if override else float(request.default_task_duration_seconds)
    distribution = override.distribution if override else "norm"
    resource_id = override.resource_id if override and override.resource_id in resource_ids else default_resource_id
    return Activity(
        element_id=task.id,
        name=task.name,
        assignments=(
            Assignment(
                resource_id=resource_id,
                duration=duration_from_mean(distribution, mean),
                provenance=_MANUAL if override else None,
            ),
        ),
    )


def _gateway(gateway: BpmnGateway, override) -> Gateway:
    flow_ids = [flow.id for flow in gateway.outgoing_flows]
    if override and override.branches:
        by_flow = {b.flow_id: float(b.probability) for b in override.branches}
        raw = [max(0.0, by_flow.get(flow_id, 0.0)) for flow_id in flow_ids]
        total = sum(raw)
        values = [value / total for value in raw] if total > 0 else [1 / len(flow_ids)] * len(flow_ids)
    else:
        values = [1 / len(flow_ids)] * len(flow_ids)
    # Senza indicazioni i rami sono equiprobabili: un'assunzione, non un dato.
    provenance = _MANUAL if override and override.branches else None
    return Gateway(
        element_id=gateway.id,
        branches=tuple(
            Branch(flow_id=flow_id, probability=value, provenance=provenance)
            for flow_id, value in zip(flow_ids, values, strict=True)
        ),
    )
