"""B1a: uno scenario Prosimos (scritto a mano o scoperto da SIMOD) dentro il Simulation IR.

E' l'inverso di ``compile.py``: ricompilato, il modello ridà gli stessi parametri.
Ogni cosa che l'IR non porta o che cambia forma finisce in ``ImportResult.notes``,
scritta per il consulente; una sezione che non sappiamo eseguire blocca l'import
con il motivo (mai un import parziale silenzioso, regola di prodotto).

Il BPMN serve per tre cose: i nomi delle attivita', i rami uscenti delle decisioni
(una porta d'unione non ha probabilita' da importare) e il tipo degli eventi
intermedi che il caso aspetta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from defusedxml import ElementTree
from pydantic import ValidationError

from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CalendarPeriod,
    CaseAttribute,
    Condition,
    DiscreteOption,
    Exponential,
    Fixed,
    Gamma,
    Gateway,
    LogNormal,
    Normal,
    PriorityRule,
    Provenance,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
    Uniform,
    Wait,
)

# Sezioni di uno scenario Prosimos che l'import sa leggere.
_SECTIONS = {
    "resource_profiles",
    "arrival_time_distribution",
    "arrival_time_calendar",
    "gateway_branching_probabilities",
    "task_resource_distribution",
    "resource_calendars",
    "event_distribution",
    "case_attributes",
    "prioritisation_rules",
}
# Metadati che SIMOD aggiunge: descrivono come e' stato scoperto lo scenario, il
# motore non li usa. Si tengono nel risultato, non nel modello.
_SIMOD_METADATA = ("process_model", "model_type", "granule_size")
# Sezioni che il motore esegue ma DeliR non ancora: con contenuto bloccano l'import.
_NOT_YET = {
    "batch_processing": "l'elaborazione a lotti (batch) non e' ancora supportata da DeliR",
    "branch_rules": "le regole sui rami vanno mappate sugli attributi del caso",
    "event_attributes": "gli aggiornamenti degli attributi alle attivita' vanno mappati",
}
_EVENT_KINDS = {
    "timerEventDefinition": "timer",
    "messageEventDefinition": "message",
    "signalEventDefinition": "signal",
    "conditionalEventDefinition": "conditional",
}
# Tolleranza per probabilita' scritte arrotondate (es. 0.3333 + 0.6667).
_ROUNDING = 1e-3

NoteKind = Literal["info", "approximated"]


class ProsimosImportError(ValueError):
    """Lo scenario non si puo' importare senza perdere o inventare qualcosa."""


@dataclass(frozen=True, slots=True)
class ImportNote:
    kind: NoteKind
    topic: str
    message: str
    element_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImportResult:
    model: SimulationModel
    notes: tuple[ImportNote, ...]
    # I metadati di SIMOD, se lo scenario viene da li'.
    simod: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Bpmn:
    names: dict[str, str] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    outgoing: dict[str, list[str]] = field(default_factory=dict)
    event_kind: dict[str, str] = field(default_factory=dict)


def import_prosimos(scenario: dict, bpmn_xml: str) -> ImportResult:
    """Il modello IR equivalente a ``scenario``, con le note per il consulente."""
    if not isinstance(scenario, dict):
        raise ProsimosImportError("Lo scenario Prosimos deve essere un oggetto JSON.")
    _check_sections(scenario)
    bpmn = _read_bpmn(bpmn_xml)
    simod = {key: scenario[key] for key in _SIMOD_METADATA if key in scenario}
    provenance = Provenance(
        origin="inferred" if simod else "manual",
        note="Scoperto da SIMOD sull'event log"
        if simod
        else "Importato da uno scenario Prosimos",
    )
    notes: list[ImportNote] = []

    calendars = [
        _calendar(entry, index)
        for index, entry in enumerate(_list(scenario, "resource_calendars"))
    ]
    arrival_calendar = Calendar(
        id=_free_id("arrival", {calendar.id for calendar in calendars}),
        name="Arrivi",
        periods=tuple(
            _period(p, f"arrival_time_calendar[{i}]")
            for i, p in enumerate(_list(scenario, "arrival_time_calendar"))
        ),
    )
    pools = [
        _pool(entry, index, provenance)
        for index, entry in enumerate(_list(scenario, "resource_profiles"))
    ]
    used = {resource.calendar_id for pool in pools for resource in pool.resources}
    for calendar in calendars:
        if calendar.id not in used:
            notes.append(
                ImportNote(
                    "info",
                    "unused_calendar",
                    f"Il calendario «{calendar.name}» non e' usato da nessuna risorsa: resta nel modello ma il motore non lo riceve.",
                    calendar.id,
                )
            )

    activities = _activities(scenario, bpmn, provenance, notes)
    gateways = _gateways(scenario, bpmn, provenance, notes)
    waits = _waits(scenario, bpmn, provenance)

    try:
        model = SimulationModel(
            arrival=Arrival(
                interarrival=_distribution(
                    scenario.get("arrival_time_distribution"),
                    "arrival_time_distribution",
                ),
                calendar_id=arrival_calendar.id,
                provenance=provenance,
            ),
            calendars=(*calendars, arrival_calendar),
            pools=tuple(pools),
            activities=tuple(activities),
            gateways=tuple(gateways),
            case_attributes=tuple(
                _case_attribute(entry, i)
                for i, entry in enumerate(scenario.get("case_attributes") or [])
            ),
            priority_rules=tuple(
                _priority(entry, i)
                for i, entry in enumerate(scenario.get("prioritisation_rules") or [])
            ),
            waits=tuple(waits),
        )
    except ValidationError as exc:
        raise ProsimosImportError(_explain(exc)) from exc
    return ImportResult(model=model, notes=tuple(notes), simod=simod)


# --------------------------------------------------------------------------- #
# Sezioni
# --------------------------------------------------------------------------- #


def _check_sections(scenario: dict) -> None:
    for key, reason in _NOT_YET.items():
        if scenario.get(key):
            raise ProsimosImportError(
                f"Sezione «{key}»: {reason}. Lo scenario non e' stato importato."
            )
    unknown = sorted(
        key
        for key, value in scenario.items()
        if key not in _SECTIONS
        and key not in _SIMOD_METADATA
        and key not in _NOT_YET
        and value not in (None, [], {})
    )
    if unknown:
        raise ProsimosImportError(
            f"Sezioni che DeliR non sa ancora leggere: {', '.join(unknown)}. Lo scenario non e' stato importato."
        )


def _read_bpmn(xml: str) -> _Bpmn:
    try:
        root = ElementTree.fromstring(xml.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - defusedxml solleva tipi diversi
        raise ProsimosImportError(
            "Il BPMN non si legge: serve il modello del processo per importare lo scenario."
        ) from exc
    bpmn = _Bpmn()
    for element in root.iter():
        tag = _local(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        bpmn.tags[element_id] = tag
        bpmn.names[element_id] = (element.attrib.get("name") or "").strip()
        if tag == "sequenceFlow" and element.attrib.get("sourceRef"):
            bpmn.outgoing.setdefault(element.attrib["sourceRef"], []).append(element_id)
        kinds = [
            _EVENT_KINDS[_local(child.tag)]
            for child in element
            if _local(child.tag) in _EVENT_KINDS
        ]
        if kinds:
            bpmn.event_kind[element_id] = kinds[0]
    return bpmn


def _activities(
    scenario: dict, bpmn: _Bpmn, provenance: Provenance, notes: list[ImportNote]
) -> list[Activity]:
    activities = []
    for index, entry in enumerate(_list(scenario, "task_resource_distribution")):
        path = f"task_resource_distribution[{index}]"
        task_id = _text(entry, "task_id", path)
        if task_id not in bpmn.tags:
            raise ProsimosImportError(f"{path}: l'attivita' {task_id} non e' nel BPMN.")
        assignments = []
        for j, resource in enumerate(_items(entry, "resources", path)):
            where = f"{path}.resources[{j}]"
            assignments.append(
                Assignment(
                    resource_id=_text(resource, "resource_id", where),
                    duration=_distribution(resource, where),
                    provenance=provenance,
                )
            )
        if not assignments:
            raise ProsimosImportError(
                f"{path}: l'attivita' {task_id} non ha nessuna risorsa che la svolga."
            )
        instant = sum(
            isinstance(a.duration, Fixed) and a.duration.value == 0 for a in assignments
        )
        name = bpmn.names.get(task_id) or task_id
        if instant:
            notes.append(
                ImportNote(
                    "info",
                    "instant_activity",
                    f"«{name}»: {instant} {'risorsa' if instant == 1 else 'risorse'} su {len(assignments)} "
                    "la svolgono in 0 secondi (attivita' istantanea nei dati).",
                    task_id,
                )
            )
        activities.append(
            Activity(
                element_id=task_id,
                name=bpmn.names.get(task_id, ""),
                assignments=tuple(assignments),
            )
        )
    return activities


def _gateways(
    scenario: dict, bpmn: _Bpmn, provenance: Provenance, notes: list[ImportNote]
) -> list[Gateway]:
    gateways = []
    for index, entry in enumerate(
        scenario.get("gateway_branching_probabilities") or []
    ):
        path = f"gateway_branching_probabilities[{index}]"
        gateway_id = _text(entry, "gateway_id", path)
        if gateway_id not in bpmn.tags:
            raise ProsimosImportError(
                f"{path}: la decisione {gateway_id} non e' nel BPMN."
            )
        declared = {}
        for j, item in enumerate(_items(entry, "probabilities", path)):
            flow = _text(item, "path_id", f"{path}.probabilities[{j}]")
            declared[flow] = _number(
                item.get("value"), f"{path}.probabilities[{j}].value"
            )
        outgoing = bpmn.outgoing.get(gateway_id, [])
        unknown = sorted(set(declared) - set(outgoing))
        if unknown:
            raise ProsimosImportError(
                f"{path}: rami che il BPMN non ha in uscita da {gateway_id}: {', '.join(unknown)}."
            )
        if len(outgoing) < 2:
            notes.append(
                ImportNote(
                    "info",
                    "merge_gateway",
                    "Porta d'unione: un solo percorso in uscita, nessuna probabilita' da impostare.",
                    gateway_id,
                )
            )
            continue
        missing = [flow for flow in outgoing if flow not in declared]
        if missing:
            notes.append(
                ImportNote(
                    "approximated",
                    "missing_branch",
                    f"{len(missing)} percorsi senza probabilita' nello scenario: valgono 0, nessun caso li prende.",
                    gateway_id,
                )
            )
        values = {flow: declared.get(flow, 0.0) for flow in outgoing}
        total = sum(values.values())
        if abs(total - 1.0) > 1e-6:
            if abs(total - 1.0) > _ROUNDING or total <= 0:
                raise ProsimosImportError(
                    f"{path}: le probabilita' di {gateway_id} sommano {total:.4f}, non 1."
                )
            values = {flow: value / total for flow, value in values.items()}
            notes.append(
                ImportNote(
                    "approximated",
                    "rounded_probabilities",
                    f"Probabilita' arrotondate (somma {total:.4f}): riportate a 1 in proporzione.",
                    gateway_id,
                )
            )
        gateways.append(
            Gateway(
                element_id=gateway_id,
                branches=tuple(
                    Branch(flow_id=flow, probability=value, provenance=provenance)
                    for flow, value in values.items()
                ),
            )
        )
    return gateways


def _waits(scenario: dict, bpmn: _Bpmn, provenance: Provenance) -> list[Wait]:
    waits = []
    for index, entry in enumerate(scenario.get("event_distribution") or []):
        path = f"event_distribution[{index}]"
        event_id = _text(entry, "event_id", path)
        if event_id not in bpmn.tags:
            raise ProsimosImportError(f"{path}: l'evento {event_id} non e' nel BPMN.")
        waits.append(
            Wait(
                element_id=event_id,
                name=bpmn.names.get(event_id, ""),
                kind=bpmn.event_kind.get(event_id, "timer"),  # type: ignore[arg-type]
                duration=_distribution(entry, path),
                provenance=provenance,
            )
        )
    return waits


def _pool(entry: Any, index: int, provenance: Provenance) -> ResourcePool:
    path = f"resource_profiles[{index}]"
    resources = []
    for j, item in enumerate(_items(entry, "resource_list", path)):
        where = f"{path}.resource_list[{j}]"
        try:
            resources.append(
                Resource(
                    id=_text(item, "id", where),
                    name=_text(item, "name", where),
                    cost_per_hour=_number(
                        item.get("cost_per_hour", 0), f"{where}.cost_per_hour"
                    ),
                    amount=int(_number(item.get("amount"), f"{where}.amount")),
                    calendar_id=_text(item, "calendar", where),
                    provenance=provenance,
                )
            )
        except ValidationError as exc:
            raise ProsimosImportError(f"{where}: {_explain(exc)}") from exc
    try:
        return ResourcePool(
            id=_text(entry, "id", path),
            name=_text(entry, "name", path),
            resources=tuple(resources),
        )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc


def _calendar(entry: Any, index: int) -> Calendar:
    path = f"resource_calendars[{index}]"
    periods = tuple(
        _period(p, f"{path}.time_periods[{i}]")
        for i, p in enumerate(_items(entry, "time_periods", path))
    )
    try:
        return Calendar(
            id=_text(entry, "id", path),
            name=_text(entry, "name", path),
            periods=periods,
        )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc


def _period(entry: Any, path: str) -> CalendarPeriod:
    if not isinstance(entry, dict):
        raise ProsimosImportError(f"{path}: periodo del calendario non valido.")
    try:
        return CalendarPeriod(
            from_day=entry.get("from"),
            to_day=entry.get("to"),
            begin=entry.get("beginTime"),
            end=entry.get("endTime"),
        )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc


def _case_attribute(entry: Any, index: int) -> CaseAttribute:
    path = f"case_attributes[{index}]"
    name = _text(entry, "name", path)
    kind = entry.get("type")
    try:
        if kind == "discrete":
            options = tuple(
                DiscreteOption(
                    value=str(option["key"]),
                    probability=_number(option.get("value"), f"{path}.values"),
                )
                for option in _items(entry, "values", path)
            )
            return CaseAttribute(name=name, options=options)
        if kind == "continuous":
            return CaseAttribute(
                name=name,
                distribution=_distribution(entry.get("values"), f"{path}.values"),
            )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc
    raise ProsimosImportError(f"{path}: tipo di attributo «{kind}» non supportato.")


def _priority(entry: Any, index: int) -> PriorityRule:
    path = f"prioritisation_rules[{index}]"
    if not isinstance(entry, dict):
        raise ProsimosImportError(f"{path}: regola di priorita' non valida.")
    groups = []
    for group in _items(entry, "rules", path):
        if not isinstance(group, list):
            raise ProsimosImportError(f"{path}: ogni gruppo di regole e' un elenco.")
        groups.append(
            tuple(
                Rule(
                    attribute=str(rule.get("attribute")),
                    operator=rule.get("comparison"),
                    value=_rule_value(rule.get("value")),
                )
                for rule in group
            )
        )
    try:
        return PriorityRule(
            level=int(_number(entry.get("priority_level"), f"{path}.priority_level")),
            condition=Condition(any_of=tuple(groups)),
        )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc


# --------------------------------------------------------------------------- #
# Distribuzioni (lo stesso formato di ``compile.distribution_params``)
# --------------------------------------------------------------------------- #


def _distribution(entry: Any, path: str):
    if not isinstance(entry, dict):
        raise ProsimosImportError(f"{path}: distribuzione mancante.")
    name = entry.get("distribution_name")
    raw = entry.get("distribution_params")
    if not isinstance(raw, list):
        raise ProsimosImportError(f"{path}: parametri della distribuzione mancanti.")
    values = [
        _number(
            item.get("value") if isinstance(item, dict) else None,
            f"{path}.distribution_params",
        )
        for item in raw
    ]
    shapes = {"fix": 1, "expon": 3, "uniform": 2, "norm": 4, "lognorm": 4, "gamma": 4}
    if name not in shapes:
        raise ProsimosImportError(
            f"{path}: la distribuzione «{name}» non e' supportata da DeliR."
        )
    if len(values) != shapes[name]:
        raise ProsimosImportError(
            f"{path}: «{name}» richiede {shapes[name]} parametri, trovati {len(values)}."
        )
    try:
        if name == "fix":
            return Fixed(value=values[0])
        if name == "expon":
            return Exponential(mean=values[0], minimum=values[1], maximum=values[2])
        if name == "uniform":
            return Uniform(minimum=values[0], maximum=values[1])
        if name == "norm":
            return Normal(
                mean=values[0], std=values[1], minimum=values[2], maximum=values[3]
            )
        if name == "lognorm":
            return LogNormal(
                mean=values[0], variance=values[1], minimum=values[2], maximum=values[3]
            )
        return Gamma(
            mean=values[0], variance=values[1], minimum=values[2], maximum=values[3]
        )
    except ValidationError as exc:
        raise ProsimosImportError(f"{path}: {_explain(exc)}") from exc


# --------------------------------------------------------------------------- #
# Lettura difensiva
# --------------------------------------------------------------------------- #


def _list(scenario: dict, key: str) -> list:
    value = scenario.get(key)
    if not isinstance(value, list):
        raise ProsimosImportError(f"Sezione «{key}» mancante o non e' un elenco.")
    return value


def _items(entry: Any, key: str, path: str) -> list:
    if not isinstance(entry, dict) or not isinstance(entry.get(key), list):
        raise ProsimosImportError(f"{path}.{key}: elenco richiesto.")
    return entry[key]


def _text(entry: Any, key: str, path: str) -> str:
    value = entry.get(key) if isinstance(entry, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ProsimosImportError(f"{path}.{key}: testo richiesto.")
    return value


def _number(value: Any, path: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProsimosImportError(f"{path}: numero non valido ({value!r}).") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ProsimosImportError(f"{path}: numero non valido ({value!r}).")
    return number


def _rule_value(value: Any) -> str | float:
    try:
        return float(value)
    except TypeError, ValueError:
        return str(value)


def _free_id(base: str, taken: set[str]) -> str:
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}_{n}"
    return candidate


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _explain(exc: ValidationError) -> str:
    return "; ".join(
        error["msg"].removeprefix("Value error, ") for error in exc.errors()
    )
