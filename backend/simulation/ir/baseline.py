"""La baseline di un processo: l'IR che si simula senza aver configurato nulla.

E' il punto di partenza che la UI mostra e a cui una patch si applica (SIM-37).
Usa le stesse assunzioni del ponte dalla richiesta storica (``from_request``) e
le risorse che il BPMN dichiara con pool e lane (SIM-09). Nessun numero qui
viene da una fonte: i parametri restano senza provenienza, cosi' il report di
readiness li conta come assunzioni e non come dati.
"""

from __future__ import annotations

from backend.schemas.simulation import CreateSimulationRunRequest, ScenarioTemplateResource
from backend.simulation.ir.from_request import (
    DEFAULT_POOL_ID,
    DEFAULT_RESOURCE_ID,
    STANDARD_CALENDAR_ID,
    duration_from_mean,
    standard_calendar,
)
from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Exponential,
    Gateway,
    Resource,
    ResourcePool,
    SimulationModel,
)
from backend.simulation.models import BpmnGateway, BpmnTask

_DEFAULTS = CreateSimulationRunRequest()


def baseline_model(
    tasks: list[BpmnTask],
    gateways: list[BpmnGateway],
    resources: list[ScenarioTemplateResource],
) -> SimulationModel:
    """Il modello di partenza del BPMN, con i default dichiarati come assunzioni."""
    if not tasks:
        raise ValueError("Il BPMN non contiene task simulabili.")
    pool = _pool(resources)
    owners = _owners(resources)
    fallback = pool.resources[0].id
    arrival_mean = float(_DEFAULTS.arrival_interval_seconds)
    return SimulationModel(
        arrival=Arrival(
            interarrival=Exponential(mean=arrival_mean, minimum=0.0, maximum=arrival_mean * 10.0),
            calendar_id=STANDARD_CALENDAR_ID,
        ),
        calendars=(standard_calendar(),),
        pools=(pool,),
        activities=tuple(
            Activity(
                element_id=task.id,
                name=task.name,
                assignments=(
                    Assignment(
                        resource_id=owners.get(task.id, fallback),
                        duration=duration_from_mean("norm", float(_DEFAULTS.default_task_duration_seconds)),
                    ),
                ),
            )
            for task in tasks
        ),
        gateways=tuple(_even_gateway(gateway) for gateway in gateways),
    )


def _pool(resources: list[ScenarioTemplateResource]) -> ResourcePool:
    if not resources:
        return ResourcePool(
            id=DEFAULT_POOL_ID,
            name=_DEFAULTS.resource_name,
            resources=(_resource(DEFAULT_RESOURCE_ID, _DEFAULTS.resource_name),),
        )
    return ResourcePool(
        id=DEFAULT_POOL_ID,
        name="Risorse",
        resources=tuple(_resource(resource.id, resource.name) for resource in resources),
    )


def _resource(resource_id: str, name: str) -> Resource:
    return Resource(
        id=resource_id,
        name=name[:120] or resource_id,
        cost_per_hour=float(_DEFAULTS.default_cost_per_hour),
        amount=int(_DEFAULTS.resource_amount),
        calendar_id=STANDARD_CALENDAR_ID,
    )


def _owners(resources: list[ScenarioTemplateResource]) -> dict[str, str]:
    # `describe_bpmn_resources` da' a ogni task al piu' un proprietario. Un task
    # ambiguo (in due lane sorelle) non ne ha: va alla prima risorsa, e il
    # consulente lo riassegna con una patch.
    owners: dict[str, str] = {}
    for resource in resources:
        for task_id in resource.task_ids:
            owners[task_id] = resource.id
    return owners


def _even_gateway(gateway: BpmnGateway) -> Gateway:
    share = 1 / len(gateway.outgoing_flows)
    return Gateway(
        element_id=gateway.id,
        branches=tuple(Branch(flow_id=flow.id, probability=share) for flow in gateway.outgoing_flows),
    )
