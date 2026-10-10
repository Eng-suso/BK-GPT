"""Simulation IR: il modello di simulazione che vive in DeliR.

Il motore (oggi Prosimos) riceve una traduzione di questo modello, non il
modello stesso: `compile.py` la produce. Qui stanno i concetti di prodotto -
distribuzioni con unita' e parametri espliciti, calendari, risorse, attivita',
rami con regole, attributi del caso - e da dove viene ogni numero
(`Provenance`, SIM-07). Un parametro senza provenienza e' un'assunzione non
dichiarata, non un errore: il report di readiness la conta.

Unita': tutte le durate sono in secondi.

Le capacita' sono quelle che lo spike G1 ha visto funzionare in Prosimos 2.1.0
(docs/simulation-prosimos-2x-spike.md). Triangolare, Weibull e Beta non ci sono
perche' il motore non le esegue: aggiungerle qui senza un modo di eseguirle
vorrebbe dire promettere qualcosa che il run non fa.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Provenienza (SIM-07)
# --------------------------------------------------------------------------- #

Origin = Literal["observed", "inferred", "declared", "estimated", "manual"]
Confidence = Literal["high", "medium", "low"]


class SourceRef(_Strict):
    """Un riferimento a cio' che sostiene il numero: un claim, una fonte, un log."""

    kind: Literal["claim", "source", "event_log", "document", "interview", "user"]
    id: str = Field(min_length=1)
    label: str | None = None


class Provenance(_Strict):
    """Da dove viene un parametro.

    - ``observed``: misurato su un event log;
    - ``inferred``: ricavato con statistica o mining;
    - ``declared``: detto in un'intervista o scritto in un documento;
    - ``estimated``: proposto da un modello AI;
    - ``manual``: inserito dal consulente.
    """

    origin: Origin
    confidence: Confidence | None = None
    sources: tuple[SourceRef, ...] = ()
    note: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Distribuzioni (secondi)
# --------------------------------------------------------------------------- #


class _Bounded(_Strict):
    minimum: float = Field(ge=0)
    maximum: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self):
        if self.minimum >= self.maximum:
            raise ValueError(f"minimo ({self.minimum}) deve essere minore del massimo ({self.maximum})")
        return self


class Fixed(_Strict):
    kind: Literal["fixed"] = "fixed"
    value: float = Field(gt=0)


class Exponential(_Bounded):
    """Media e limiti. Prosimos usa ``scale = mean - minimum``, ``loc = minimum``."""

    kind: Literal["exponential"] = "exponential"
    mean: float = Field(gt=0)

    @model_validator(mode="after")
    def _mean_inside(self):
        if not self.minimum < self.mean < self.maximum:
            raise ValueError("la media deve stare fra minimo e massimo")
        return self


class Uniform(_Bounded):
    kind: Literal["uniform"] = "uniform"


class Normal(_Bounded):
    kind: Literal["normal"] = "normal"
    mean: float = Field(gt=0)
    std: float = Field(gt=0)

    @model_validator(mode="after")
    def _mean_inside(self):
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("la media deve stare fra minimo e massimo")
        return self


class LogNormal(_Bounded):
    kind: Literal["lognormal"] = "lognormal"
    mean: float = Field(gt=0)
    variance: float = Field(gt=0)


class Gamma(_Bounded):
    kind: Literal["gamma"] = "gamma"
    mean: float = Field(gt=0)
    variance: float = Field(gt=0)


Distribution = Annotated[
    Fixed | Exponential | Uniform | Normal | LogNormal | Gamma,
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Calendari
# --------------------------------------------------------------------------- #

Weekday = Literal["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d{1,3})?$")


class CalendarPeriod(_Strict):
    """Da un giorno a un altro (inclusi), fra due orari dello stesso giorno.

    Un turno notturno sono due periodi (22:00-23:59:59 e 00:00-06:00 del giorno
    dopo); la giornata intera e' 00:00:00-23:59:59, perche' 24:00 non e' un orario.
    """

    from_day: Weekday
    to_day: Weekday
    begin: str
    end: str

    @model_validator(mode="after")
    def _valid_times(self):
        for value in (self.begin, self.end):
            if not _TIME.match(value):
                raise ValueError(f"orario non valido: {value!r} (atteso HH:MM:SS)")
        if self.begin[:8] >= self.end[:8]:
            raise ValueError(
                f"{self.begin}-{self.end}: un periodo che passa la mezzanotte va diviso in due"
            )
        return self


class Calendar(_Strict):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    periods: tuple[CalendarPeriod, ...] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Risorse e attivita'
# --------------------------------------------------------------------------- #


class Resource(_Strict):
    """Un tipo di risorsa con il suo organico: ``amount`` unita' identiche."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    cost_per_hour: float = Field(ge=0)
    amount: int = Field(ge=1, le=1000)
    calendar_id: str
    provenance: Provenance | None = None


class ResourcePool(_Strict):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    resources: tuple[Resource, ...] = Field(min_length=1)


class Assignment(_Strict):
    """Chi puo' svolgere l'attivita', e quanto ci mette quella risorsa."""

    resource_id: str
    duration: Distribution
    provenance: Provenance | None = None


class DurationVariant(_Strict):
    """La durata dell'attivita' per i casi con ``attribute = value``."""

    value: str = Field(min_length=1)
    duration: Distribution
    provenance: Provenance | None = None


class DurationByAttribute(_Strict):
    """SIM-32: la durata cambia con un attributo a categorie del caso.

    Un caso con una categoria elencata usa la sua durata; gli altri usano quelle
    delle assegnazioni. Il motore non lo sa fare: ``ir/variants.py`` compila
    l'attivita' in varianti dietro una decisione per regola.
    """

    attribute: str = Field(min_length=1, max_length=64)
    variants: tuple[DurationVariant, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _distinct(self):
        _unique(f"categoria della durata per {self.attribute}", [variant.value for variant in self.variants])
        return self


class Activity(_Strict):
    element_id: str = Field(min_length=1)
    name: str = ""
    assignments: tuple[Assignment, ...] = Field(min_length=1)
    duration_by: DurationByAttribute | None = None


# --------------------------------------------------------------------------- #
# Regole, rami, attributi
# --------------------------------------------------------------------------- #

Operator = Literal[">", ">=", "<", "<=", "=", "!="]


class Rule(_Strict):
    attribute: str = Field(min_length=1)
    operator: Operator
    value: str | float


class Condition(_Strict):
    """Vera se almeno un gruppo e' vero; un gruppo e' vero se tutte le sue regole lo sono."""

    any_of: tuple[tuple[Rule, ...], ...] = Field(min_length=1)

    def attributes(self) -> set[str]:
        return {rule.attribute for group in self.any_of for rule in group}


class Branch(_Strict):
    flow_id: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    condition: Condition | None = None
    provenance: Provenance | None = None


class Gateway(_Strict):
    element_id: str = Field(min_length=1)
    branches: tuple[Branch, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _consistent(self):
        flows = [branch.flow_id for branch in self.branches]
        if len(set(flows)) != len(flows):
            raise ValueError(f"gateway {self.element_id}: un ramo compare due volte")
        conditional = [branch.condition is not None for branch in self.branches]
        if any(conditional) and not all(conditional):
            # Prosimos instrada per regola solo se ogni ramo ne ha una: con un ramo
            # scoperto il caso che non soddisfa nessuna regola non avrebbe uscita.
            raise ValueError(f"gateway {self.element_id}: o tutti i rami hanno una regola o nessuno")
        if not any(conditional):
            total = sum(branch.probability for branch in self.branches)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"gateway {self.element_id}: le probabilita' sommano {total:.4f}, non 1")
        return self


class DiscreteOption(_Strict):
    value: str = Field(min_length=1)
    probability: float = Field(gt=0, le=1)


class CaseAttribute(_Strict):
    """Un attributo che ogni caso riceve all'arrivo."""

    name: str = Field(min_length=1, max_length=64)
    options: tuple[DiscreteOption, ...] | None = None
    distribution: Distribution | None = None
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.options is None) == (self.distribution is None):
            raise ValueError(f"attributo {self.name}: o opzioni discrete o una distribuzione")
        if self.options is not None:
            total = sum(option.probability for option in self.options)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"attributo {self.name}: le probabilita' sommano {total:.4f}, non 1")
        return self


class AttributeUpdate(_Strict):
    """Quando il caso completa ``element_id``, ``name`` diventa ``expression``.

    L'espressione e' quella di Prosimos (aritmetica sugli attributi del caso).
    """

    element_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    expression: str = Field(min_length=1, max_length=500)


class PriorityRule(_Strict):
    """Livello 1 = servito per primo. I casi che non soddisfano nessuna regola vanno in coda."""

    level: int = Field(ge=1)
    condition: Condition


class Arrival(_Strict):
    interarrival: Distribution
    calendar_id: str
    provenance: Provenance | None = None


# --------------------------------------------------------------------------- #
# Il modello
# --------------------------------------------------------------------------- #


class SimulationModel(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    arrival: Arrival
    calendars: tuple[Calendar, ...] = Field(min_length=1)
    pools: tuple[ResourcePool, ...] = Field(min_length=1)
    activities: tuple[Activity, ...] = Field(min_length=1)
    gateways: tuple[Gateway, ...] = ()
    case_attributes: tuple[CaseAttribute, ...] = ()
    attribute_updates: tuple[AttributeUpdate, ...] = ()
    priority_rules: tuple[PriorityRule, ...] = ()

    def resources(self) -> dict[str, Resource]:
        return {resource.id: resource for pool in self.pools for resource in pool.resources}

    @model_validator(mode="after")
    def _references(self):
        calendars = [calendar.id for calendar in self.calendars]
        _unique("calendario", calendars)
        _unique("pool", [pool.id for pool in self.pools])
        resource_ids = [r.id for pool in self.pools for r in pool.resources]
        _unique("risorsa", resource_ids)
        _unique("attivita'", [activity.element_id for activity in self.activities])
        _unique("gateway", [gateway.element_id for gateway in self.gateways])
        _unique("attributo", [attribute.name for attribute in self.case_attributes])

        known_calendars = set(calendars)
        if self.arrival.calendar_id not in known_calendars:
            raise ValueError(f"calendario degli arrivi sconosciuto: {self.arrival.calendar_id}")
        for resource in self.resources().values():
            if resource.calendar_id not in known_calendars:
                raise ValueError(f"risorsa {resource.id}: calendario sconosciuto {resource.calendar_id}")

        known_resources = set(resource_ids)
        for activity in self.activities:
            seen = [assignment.resource_id for assignment in activity.assignments]
            _unique(f"assegnazione in {activity.element_id}", seen)
            for resource_id in seen:
                if resource_id not in known_resources:
                    raise ValueError(f"attivita' {activity.element_id}: risorsa sconosciuta {resource_id}")

        attributes = {attribute.name for attribute in self.case_attributes}
        attributes |= {update.name for update in self.attribute_updates}
        conditions = [b.condition for g in self.gateways for b in g.branches if b.condition]
        conditions += [rule.condition for rule in self.priority_rules]
        for condition in conditions:
            missing = condition.attributes() - attributes
            if missing:
                raise ValueError(f"regola su attributi che il caso non ha: {', '.join(sorted(missing))}")
        return self


def _unique(what: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{what} duplicato: {', '.join(duplicates)}")
