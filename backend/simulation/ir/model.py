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


class ResourceShift(_Strict):
    """SIM-30: ``amount`` unita' in piu' della risorsa, presenti solo nel calendario ``calendar_id``.

    "Due operatori tutto il giorno, due in piu' dalle 9 alle 12" e' una risorsa
    con ``amount=2`` e un turno con ``amount=2`` sul calendario 9-12. Il motore
    non conosce organici che cambiano nel tempo: la compilazione fa del turno
    una risorsa in piu', con le stesse attivita' e le stesse durate.
    """

    amount: int = Field(ge=1, le=1000)
    calendar_id: str
    provenance: Provenance | None = None


class Resource(_Strict):
    """Un tipo di risorsa con il suo organico: ``amount`` unita' identiche.

    SIM-09b: ``kind="system"`` e' un sistema o una macchina (un ERP, un robot
    RPA): ``amount`` sono le esecuzioni contemporanee, niente turni. Per il
    motore e' una risorsa come le altre; la differenza la dicono pannello,
    inspector e risultati.
    """

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    cost_per_hour: float = Field(ge=0)
    amount: int = Field(ge=1, le=1000)
    calendar_id: str
    provenance: Provenance | None = None
    shifts: tuple[ResourceShift, ...] = Field(default=(), max_length=10)
    kind: Literal["person", "system"] = "person"

    @model_validator(mode="after")
    def _system_without_shifts(self):
        if self.kind == "system" and self.shifts:
            raise ValueError(f"risorsa {self.id}: un sistema non ha turni di rinforzo, ha esecuzioni contemporanee")
        return self


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
    """La durata dell'attivita' per i casi con ``attribute = value`` (categorie)
    oppure con ``attribute`` sotto ``up_to`` e sopra la soglia precedente (numeri)."""

    value: str | None = Field(default=None, min_length=1)
    up_to: float | None = None
    duration: Distribution
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _one_key(self):
        if (self.value is None) == (self.up_to is None):
            raise ValueError("una durata per categoria ha o una categoria o una soglia")
        return self


class DurationByAttribute(_Strict):
    """SIM-32: la durata cambia con un attributo del caso.

    A categorie: un caso con una categoria elencata usa la sua durata. Numerico:
    soglie crescenti, "fino a 1.000", "fino a 5.000"; un caso usa la durata della
    prima soglia che non raggiunge. Gli altri casi usano quelle delle
    assegnazioni. Il motore non lo sa fare: ``ir/variants.py`` compila
    l'attivita' in varianti dietro una decisione per regola.
    """

    attribute: str = Field(min_length=1, max_length=64)
    variants: tuple[DurationVariant, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _distinct(self):
        thresholds = [variant.up_to for variant in self.variants if variant.up_to is not None]
        if thresholds and len(thresholds) != len(self.variants):
            raise ValueError(f"durate per {self.attribute}: o tutte per categoria o tutte per soglia")
        if thresholds:
            # Fasce consecutive: ognuna va dalla soglia precedente alla sua.
            if any(b <= a for a, b in zip(thresholds, thresholds[1:], strict=False)):
                raise ValueError(f"durate per {self.attribute}: le soglie devono crescere")
            return self
        _unique(f"categoria della durata per {self.attribute}", [variant.value or "" for variant in self.variants])
        return self

    @property
    def by_threshold(self) -> bool:
        return self.variants[0].up_to is not None


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


class Skip(_Strict):
    """SIM-35: una parte dei casi salta l'attivita'.

    Senza ``condition`` la salta una quota ``probability`` di tutti i casi; con
    una condizione, la stessa quota dei soli casi che la soddisfano (1 = tutti
    loro). Il motore non lo sa fare: ``ir/flow_rules.py`` mette davanti
    all'attivita' una decisione con un ramo che la scavalca.
    """

    probability: float = Field(gt=0, le=1)
    condition: Condition | None = None
    provenance: Provenance | None = None


class Rework(_Strict):
    """SIM-35: dopo l'attivita' una parte dei casi torna indietro e rifa' il lavoro.

    ``back_to`` e' l'attivita' da cui si riparte (anche questa stessa). Ogni
    passaggio torna indietro con ``probability``, al piu' ``max_repeats`` volte
    per caso; con ``condition`` torna indietro solo chi la soddisfa.
    """

    back_to: str = Field(min_length=1)
    probability: float = Field(gt=0, lt=1)
    max_repeats: int = Field(ge=1, le=10)
    condition: Condition | None = None
    provenance: Provenance | None = None


class DurationWindow(CalendarPeriod):
    """SIM-33b: un'attivita' che inizia in questa fascia dura ``factor`` volte tanto.

    "Dopo le 16 una pratica richiede il 30% in piu'" e' ``factor`` 1,3 dalle
    16 alle 17:59:59. Conta l'ora d'inizio; fuori da ogni fascia la durata e'
    quella delle assegnazioni. Prosimos 2.1 non lo sa fare: lo applica il
    runner DeliR (``ops/prosimos/runner/duration_windows.py``). Un'escalation a
    tempo (SIM-35b) resta calcolata sulla durata senza fasce: il timer conta
    l'orologio, non il ritmo di lavoro.
    """

    factor: float = Field(gt=0, le=10)
    provenance: Provenance | None = None


class Activity(_Strict):
    element_id: str = Field(min_length=1)
    name: str = ""
    assignments: tuple[Assignment, ...] = Field(min_length=1)
    duration_by: DurationByAttribute | None = None
    skip: Skip | None = None
    rework: Rework | None = None
    duration_windows: tuple[DurationWindow, ...] = Field(default=(), max_length=21)
    # SIM-11f: una multi-istanza con un numero fisso: ogni caso la esegue
    # ``instances`` volte, una dopo l'altra o in parallelo (``ir/instances.py``).
    instances: int = Field(default=1, ge=1, le=50)
    sequential_instances: bool = True

    @model_validator(mode="after")
    def _windows_apart(self):
        _check_apart(self.duration_windows, f"attivita' {self.element_id}: due fasce della durata si sovrappongono")
        return self


class Wait(_Strict):
    """SIM-11c/d: un evento intermedio che il caso aspetta.

    L'attesa conta l'orologio, non il calendario: un timer di 48 ore scade dopo
    48 ore anche nel fine settimana. Nessuna risorsa la svolge. Un timer porta
    la durata dal BPMN; per un messaggio o un segnale la imposta il consulente,
    e senza (``duration`` assente) il caso prosegue subito. Il motore la riceve
    in ``event_distribution``.
    """

    element_id: str = Field(min_length=1)
    name: str = ""
    kind: Literal["timer", "message", "signal", "conditional"] = "timer"
    duration: Distribution | None = None
    provenance: Provenance | None = None


# --------------------------------------------------------------------------- #
# Regole, rami, attributi
# --------------------------------------------------------------------------- #

class Branch(_Strict):
    flow_id: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    condition: Condition | None = None
    provenance: Provenance | None = None


class TimerEscalation(_Strict):
    """SIM-35: la decisione era un timer interrompente sul bordo di un'attivita'.

    Il caso prende il ramo d'escalation se l'attivita' dura piu' di
    ``after_seconds``; le probabilita' dei rami non contano, le calcola
    ``ir/escalations.py`` dalla durata. Approssimazione dichiarata: il timer
    conta la lavorazione, non l'attesa in coda davanti all'attivita'.
    """

    activity_id: str = Field(min_length=1)
    after_seconds: float = Field(gt=0)
    normal_flow_id: str = Field(min_length=1)
    # SIM-11g: un timer non interrompente. L'attivita' continua; la decisione sta
    # su un ramo parallelo che aspetta ``after_seconds``, e il ramo normale
    # chiude quel ramo senza fare nulla.
    interrupting: bool = True


class Gateway(_Strict):
    element_id: str = Field(min_length=1)
    branches: tuple[Branch, ...] = Field(min_length=2)
    escalation: TimerEscalation | None = None

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
        if self.escalation is not None:
            if any(conditional) or len(flows) != 2 or self.escalation.normal_flow_id not in flows:
                raise ValueError(f"gateway {self.element_id}: un'escalation ha il ramo normale e quello d'escalation, senza regole")
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
    """Quando il caso completa ``element_id``, ``name`` cambia valore.

    Con ``expression`` diventa il risultato dell'espressione di Prosimos
    (aritmetica sugli attributi del caso); con ``options`` (SIM-31b, l'esito
    dell'attivita') una delle categorie, scelta con la sua probabilita'.
    """

    element_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    expression: str | None = Field(default=None, min_length=1, max_length=500)
    options: tuple[DiscreteOption, ...] | None = None
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.expression is None) == (self.options is None):
            raise ValueError(f"aggiornamento di {self.name}: o un'espressione o delle categorie")
        if self.options is not None:
            _unique(f"categoria di {self.name}", [option.value for option in self.options])
            total = sum(option.probability for option in self.options)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"aggiornamento di {self.name}: le probabilita' sommano {total:.4f}, non 1")
        return self


class PriorityRule(_Strict):
    """Livello 1 = servito per primo. I casi che non soddisfano nessuna regola vanno in coda."""

    level: int = Field(ge=1)
    condition: Condition


class ArrivalBand(CalendarPeriod):
    """SIM-08: in questa fascia i casi arrivano in media ogni ``mean_seconds``.

    Dentro la fascia gli arrivi sono un processo di Poisson; fuori da ogni
    fascia non arriva nessuno. Prosimos 2.1 non lo sa fare: li genera il runner
    DeliR (``ops/prosimos/runner/arrival_bands.py``).
    """

    mean_seconds: float = Field(gt=0)


class MonthFactor(_Strict):
    """SIM-08b: nel mese ``month`` (1 = gennaio) i casi arrivano ``factor`` volte
    piu' spesso ("dicembre +40%" = 1,4; "agosto -50%" = 0,5)."""

    month: int = Field(ge=1, le=12)
    factor: float = Field(gt=0, le=10)


class Arrival(_Strict):
    interarrival: Distribution
    calendar_id: str
    provenance: Provenance | None = None
    # Con delle fasce, gli arrivi seguono loro e non piu' interarrival e calendario.
    bands: tuple[ArrivalBand, ...] = Field(default=(), max_length=21)
    # SIM-33: l'attributo del caso che riceve la fascia di arrivo ("Fascia 1", ...).
    # Lo riempie il runner; durate per categoria e regole lo leggono come gli altri.
    band_attribute: str | None = Field(default=None, min_length=1, max_length=64)
    # SIM-08b: il ritmo cambia con il mese. Lo applica il runner sugli arrivi per
    # fascia; senza fasce gli arrivi devono essere esponenziali, e le fasce sono
    # i periodi del calendario degli arrivi (``SimulationModel.arrival_bands``).
    months: tuple[MonthFactor, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _bands_apart(self):
        if self.band_attribute and not self.bands:
            raise ValueError("la fascia di arrivo come attributo richiede delle fasce degli arrivi")
        _check_apart(self.bands, "due fasce degli arrivi si sovrappongono")
        _unique("mese degli arrivi", [str(m.month) for m in self.months])
        if self.months and not self.bands and not isinstance(self.interarrival, Exponential):
            raise ValueError("il ritmo per mese vale con le fasce degli arrivi o con arrivi esponenziali")
        return self


def band_label(index: int) -> str:
    """Il valore della fascia ``index`` (da 0): lo stesso che scrive il runner."""
    return f"Fascia {index + 1}"


def _check_band_attribute(arrival: "Arrival", case_attributes: "tuple[CaseAttribute, ...]") -> None:
    """L'attributo della fascia ha come categorie esattamente le fasce, nel loro ordine."""
    name = arrival.band_attribute
    attribute = next((a for a in case_attributes if a.name == name), None)
    expected = [band_label(i) for i in range(len(arrival.bands))]
    if attribute is None or attribute.options is None:
        raise ValueError(f"la fascia di arrivo va in un attributo a categorie del caso: {name} non c'e'")
    if [option.value for option in attribute.options] != expected:
        raise ValueError(f"attributo {name}: le categorie devono essere le fasce degli arrivi, {', '.join(expected)}")


_WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _check_apart(periods: "tuple[CalendarPeriod, ...]", message: str) -> None:
    """Fasce della settimana che non si toccano: un istante sta al piu' in una."""
    intervals = sorted(
        (day * 86_400 + _clock(period.begin), day * 86_400 + _clock(period.end))
        for period in periods
        for day in _days(period.from_day, period.to_day)
    )
    for (_, end), (begin, _) in zip(intervals, intervals[1:], strict=False):
        if begin < end:
            raise ValueError(message)


def _days(first: str, last: str) -> list[int]:
    start, end = _WEEKDAYS.index(first), _WEEKDAYS.index(last)
    return list(range(start, end + 1)) if start <= end else [*range(start, 7), *range(0, end + 1)]


def _clock(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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
    # SIM-11c: i timer intermedi del BPMN che il caso aspetta.
    waits: tuple[Wait, ...] = ()

    def resources(self) -> dict[str, Resource]:
        return {resource.id: resource for pool in self.pools for resource in pool.resources}

    def arrival_bands(self) -> tuple[ArrivalBand, ...]:
        """Le fasce da cui il runner genera gli arrivi, o nessuna se li genera il motore.

        SIM-08b: un ritmo per mese senza fasce trasforma i periodi del calendario
        degli arrivi in fasce con la media degli arrivi esponenziali: lo stesso
        processo di Poisson, che il runner sa scalare mese per mese.
        """
        if self.arrival.bands or not self.arrival.months:
            return self.arrival.bands
        assert isinstance(self.arrival.interarrival, Exponential)
        calendar = next(c for c in self.calendars if c.id == self.arrival.calendar_id)
        return tuple(ArrivalBand(**period.model_dump(), mean_seconds=self.arrival.interarrival.mean)
                     for period in calendar.periods)

    @model_validator(mode="after")
    def _references(self):
        calendars = [calendar.id for calendar in self.calendars]
        _unique("calendario", calendars)
        _unique("pool", [pool.id for pool in self.pools])
        resource_ids = [r.id for pool in self.pools for r in pool.resources]
        _unique("risorsa", resource_ids)
        _unique("attivita'", [activity.element_id for activity in self.activities])
        _unique("gateway", [gateway.element_id for gateway in self.gateways])
        _unique("attesa", [wait.element_id for wait in self.waits])
        _unique("attributo", [attribute.name for attribute in self.case_attributes])

        known_calendars = set(calendars)
        if self.arrival.calendar_id not in known_calendars:
            raise ValueError(f"calendario degli arrivi sconosciuto: {self.arrival.calendar_id}")
        for resource in self.resources().values():
            if resource.calendar_id not in known_calendars:
                raise ValueError(f"risorsa {resource.id}: calendario sconosciuto {resource.calendar_id}")
            for shift in resource.shifts:
                if shift.calendar_id not in known_calendars:
                    raise ValueError(f"risorsa {resource.id}: turno su un calendario sconosciuto {shift.calendar_id}")

        known_resources = set(resource_ids)
        for activity in self.activities:
            seen = [assignment.resource_id for assignment in activity.assignments]
            _unique(f"assegnazione in {activity.element_id}", seen)
            for resource_id in seen:
                if resource_id not in known_resources:
                    raise ValueError(f"attivita' {activity.element_id}: risorsa sconosciuta {resource_id}")

        activity_ids = {activity.element_id for activity in self.activities}
        for gateway in self.gateways:
            if gateway.escalation and gateway.escalation.activity_id not in activity_ids:
                raise ValueError(f"gateway {gateway.element_id}: l'escalation e' su {gateway.escalation.activity_id}, che non e' un'attivita'")
        for activity in self.activities:
            if activity.rework and activity.rework.back_to not in activity_ids:
                raise ValueError(
                    f"attivita' {activity.element_id}: la rilavorazione torna a {activity.rework.back_to}, che non e' un'attivita'"
                )

        if self.arrival.band_attribute:
            _check_band_attribute(self.arrival, self.case_attributes)

        attributes = {attribute.name for attribute in self.case_attributes}
        overwritten = sorted(attributes & {update.name for update in self.attribute_updates})
        if overwritten:
            # Prosimos rifiuta lo scenario: un evento non cambia un attributo del caso.
            raise ValueError(f"un'attivita' non puo' cambiare un attributo del caso: {', '.join(overwritten)}")
        attributes |= {update.name for update in self.attribute_updates}
        conditions = [b.condition for g in self.gateways for b in g.branches if b.condition]
        conditions += [rule.condition for rule in self.priority_rules]
        conditions += [a.skip.condition for a in self.activities if a.skip and a.skip.condition]
        conditions += [a.rework.condition for a in self.activities if a.rework and a.rework.condition]
        for condition in conditions:
            missing = condition.attributes() - attributes
            if missing:
                raise ValueError(f"regola su attributi che il caso non ha: {', '.join(sorted(missing))}")
        return self


def _unique(what: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{what} duplicato: {', '.join(duplicates)}")
