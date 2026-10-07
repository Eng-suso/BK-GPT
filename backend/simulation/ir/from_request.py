"""Dalla richiesta di oggi (``CreateSimulationRunRequest``) al Simulation IR.

E' il ponte: la UI manda medie, le sei distribuzioni di Prosimos 2.1 con i loro
parametri facoltativi, una risorsa per attivita' e i calendari delle risorse;
qui diventano un modello esplicito, con le assunzioni del builder storico rese
visibili e marcate ``manual``. Senza parametri e calendari nuovi il risultato
compilato e' identico allo scenario che il builder produceva (test di
equivalenza).
"""

from __future__ import annotations

from pydantic import ValidationError

from backend.schemas.simulation import CreateSimulationRunRequest, SimCalendarConfig, SimTaskConfig
from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CalendarPeriod,
    Distribution,
    Exponential,
    Fixed,
    Gamma,
    Gateway,
    LogNormal,
    Normal,
    Provenance,
    Resource,
    ResourcePool,
    SimulationModel,
    Uniform,
)
from backend.simulation.models import BpmnGateway, BpmnTask

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
    calendars = _calendars(request.calendars or [])
    pool = _pool(request, tasks, task_overrides, {calendar.id for calendar in calendars})
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
        calendars=calendars,
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
    return duration(distribution, mean)


def duration(
    distribution: str,
    mean: float,
    *,
    std: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> Distribution:
    """La durata con i parametri del consulente; quelli che mancano seguono le
    assunzioni storiche (``duration_from_mean``).

    Raises:
        ValueError: parametri incoerenti (limiti invertiti, media fuori dai limiti,
            uniforme senza minimo e massimo), con un messaggio per il consulente.
    """
    mean = max(1.0, mean)
    try:
        if distribution == "fixed":
            return Fixed(value=mean)
        if distribution == "expon":
            return Exponential(
                mean=mean,
                minimum=0.0 if minimum is None else minimum,
                maximum=mean * 10.0 if maximum is None else maximum,
            )
        if distribution == "uniform":
            if minimum is None or maximum is None:
                raise ValueError("Per la distribuzione uniforme indica minimo e massimo.")
            return Uniform(minimum=minimum, maximum=maximum)
        sigma = std if std is not None else max(1.0, mean * 0.1)
        low = max(0.0, mean - 3.0 * sigma) if minimum is None else minimum
        high = mean + 3.0 * sigma if maximum is None else maximum
        if distribution == "norm":
            return Normal(mean=mean, std=sigma, minimum=low, maximum=high)
        if distribution == "lognorm":
            return LogNormal(mean=mean, variance=sigma**2, minimum=low, maximum=high)
        if distribution == "gamma":
            return Gamma(mean=mean, variance=sigma**2, minimum=low, maximum=high)
    except ValidationError as exc:
        reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise ValueError(f"Durata non valida ({distribution}): {reason}.") from exc
    raise ValueError(f"Distribuzione non supportata: {distribution}.")


def _task_duration(override: SimTaskConfig) -> Distribution:
    return duration(
        override.distribution,
        float(override.mean_seconds),
        std=override.std_seconds,
        minimum=override.min_seconds,
        maximum=override.max_seconds,
    )


def _calendars(configs: list[SimCalendarConfig]) -> tuple[Calendar, ...]:
    """Il calendario standard (arrivi e risorse senza calendario) piu' quelli del consulente."""
    ids = [config.id for config in configs]
    if STANDARD_CALENDAR_ID in ids or len(set(ids)) != len(ids):
        raise ValueError("I calendari devono avere identificativi distinti.")
    calendars = [standard_calendar()]
    for config in configs:
        try:
            calendars.append(Calendar(
                id=config.id,
                name=config.name,
                periods=tuple(
                    CalendarPeriod(
                        from_day=period.from_day,
                        to_day=period.to_day,
                        begin=_clock(period.begin),
                        end=_clock(period.end),
                    )
                    for period in config.periods
                ),
            ))
        except ValidationError as exc:
            reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
            raise ValueError(f"Calendario «{config.name}» non valido: {reason}.") from exc
    return tuple(calendars)


def _clock(value: str) -> str:
    """``HH:MM`` diventa ``HH:MM:00.000``; il resto lo valida il modello."""
    return f"{value}:00.000" if len(value) == 5 else value


def _pool(
    request: CreateSimulationRunRequest,
    tasks: list[BpmnTask],
    task_overrides: dict,
    calendar_ids: set[str],
) -> ResourcePool:
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
        unknown = sorted({cfg.calendar_id for cfg in request.resources if cfg.calendar_id} - calendar_ids)
        if unknown:
            raise ValueError(f"Calendari inesistenti assegnati alle risorse: {', '.join(unknown)}.")
        return ResourcePool(
            id=DEFAULT_POOL_ID,
            name="Risorse",
            resources=tuple(
                Resource(
                    id=cfg.id,
                    name=cfg.name,
                    cost_per_hour=float(cfg.cost_per_hour),
                    amount=int(cfg.amount),
                    calendar_id=cfg.calendar_id or STANDARD_CALENDAR_ID,
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
    duration_ = _task_duration(override) if override else duration_from_mean(
        "norm", float(request.default_task_duration_seconds)
    )
    resource_id = override.resource_id if override and override.resource_id in resource_ids else default_resource_id
    return Activity(
        element_id=task.id,
        name=task.name,
        assignments=(
            Assignment(
                resource_id=resource_id,
                duration=duration_,
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
