"""Uno scenario Prosimos (JSON) come bozza del pannello, con cio' che non entra dichiarato.

Gemello di ``importProsimosJson`` in ``frontend/.../simulation/prosimosJson.ts``:
i casi di ``tests/fixtures/simulation/prosimos_import_cases.json`` valgono per
entrambi, cambiando uno il test dell'altro fallisce. Serve al server per
importare scenari senza browser (harness di valutazione, API).

Qualsiasi JSON Prosimos deve entrare. Le regole:

- le sei sezioni di base (risorse, calendari, durate, decisioni, arrivi, attese)
  si traducono; un loro valore che non si puo' simulare e' un errore con il
  percorso del campo;
- i metadati noti degli scenari scoperti da SIMOD (``process_model``,
  ``model_type``, ``granule_size``) si ignorano;
- le sezioni che la bozza non rappresenta ancora (batch, attributi, regole...)
  non bloccano: restano fuori e lo dice un avviso ``notImported``;
- un campo sconosciuto dentro una riga si ignora con un avviso ``ignoredField``;
- probabilita' di una decisione che non sommano a 1 si normalizzano con un
  avviso ``normalizedProbabilities``;
- un gateway con un solo percorso a probabilita' 1 (il join che Prosimos
  elenca comunque) non e' una decisione: si ignora con ``ignoredGateway``.

Le durate di Prosimos sono in secondi, la bozza in minuti. ``lognorm`` e
``gamma`` portano la varianza (pix-framework), la bozza la deviazione standard.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Any

from backend.schemas.simulation import ScenarioTemplateResponse
from backend.simulation.draft_request import DEFAULT_SCENARIO

CORE_SECTIONS = (
    "resource_profiles", "arrival_time_distribution", "arrival_time_calendar",
    "gateway_branching_probabilities", "task_resource_distribution", "resource_calendars",
    "event_distribution",
)
#: Metadati degli scenari SIMOD: non cambiano cosa si simula.
METADATA_SECTIONS = ("process_model", "model_type", "granule_size")
DISTRIBUTIONS = {
    "fix": "fixed", "fixed": "fixed", "expon": "expon", "uniform": "uniform",
    "norm": "norm", "lognorm": "lognorm", "gamma": "gamma",
}
PARAMETER_COUNT = {"fixed": 1, "uniform": 2, "expon": 3, "norm": 4, "lognorm": 4, "gamma": 4}
_DAY = re.compile(r"^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$")
_TRAILING_ZERO_SECONDS = re.compile(r"(?::00(?:\.0{1,3})?)$")
ARRIVAL_CALENDAR_ID = "imported-arrival-calendar"
PROBABILITY_TOLERANCE = 0.001


class ProsimosImportError(ValueError):
    """Lo scenario non si puo' simulare cosi' com'e': il messaggio dice dove."""


@dataclass
class ProsimosImport:
    draft: dict[str, Any]
    warnings: list[dict[str, str]] = field(default_factory=list)


def flow_mapping_key(gateway_id: str, flow_id: str) -> str:
    return f"{gateway_id}::{flow_id}"


class _Reader:
    """Letture tipizzate che raccolgono gli avvisi sui campi ignorati."""

    def __init__(self) -> None:
        self.warnings: list[dict[str, str]] = []

    def warn(self, kind: str, target: str) -> None:
        entry = {"kind": kind, "target": target}
        if entry not in self.warnings:
            self.warnings.append(entry)

    @staticmethod
    def object(value: Any, path: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ProsimosImportError(f"{path}: oggetto richiesto.")
        return value

    @staticmethod
    def list(value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            raise ProsimosImportError(f"{path}: elenco richiesto.")
        return value

    @staticmethod
    def string(value: Any, path: str) -> str:
        if not isinstance(value, str) or not value:
            raise ProsimosImportError(f"{path}: testo richiesto.")
        return value

    @staticmethod
    def number(value: Any, path: str) -> float:
        result = math.nan
        if isinstance(value, bool):
            result = math.nan
        elif isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str) and value.strip():
            try:
                result = float(value)
            except ValueError:
                result = math.nan
        if not math.isfinite(result):
            raise ProsimosImportError(f"{path}: numero non valido.")
        return result

    def keys(self, value: dict[str, Any], allowed: tuple[str, ...], path: str) -> None:
        for key in value:
            if key not in allowed:
                self.warn("ignoredField", f"{path}.{key}")

    def duration(self, value: Any, path: str) -> dict[str, Any]:
        distribution = self.object(value, path)
        self.keys(distribution, ("distribution_name", "distribution_params"), path)
        raw_name = self.string(distribution.get("distribution_name"), f"{path}.distribution_name")
        name = DISTRIBUTIONS.get(raw_name)
        if name is None:
            raise ProsimosImportError(f"{path}: distribuzione {raw_name} non supportata dal motore.")
        params = []
        for index, entry in enumerate(self.list(distribution.get("distribution_params"), f"{path}.distribution_params")):
            row = self.object(entry, f"{path}.distribution_params[{index}]")
            self.keys(row, ("value",), f"{path}.distribution_params[{index}]")
            params.append(self.number(row.get("value"), f"{path}.distribution_params[{index}].value"))
        count = PARAMETER_COUNT[name]
        if len(params) != count:
            raise ProsimosImportError(f"{path}: {name} richiede {count} parametri, trovati {len(params)}.")
        if name == "uniform":
            return {"distribution": name, "meanMinutes": (params[0] + params[1]) / 120,
                    "minMinutes": params[0] / 60, "maxMinutes": params[1] / 60}
        if name == "fixed":
            return {"distribution": name, "meanMinutes": params[0] / 60}
        if name == "expon":
            return {"distribution": name, "meanMinutes": params[0] / 60,
                    "minMinutes": params[1] / 60, "maxMinutes": params[2] / 60}
        std = params[1] if name == "norm" else math.sqrt(params[1])
        return {"distribution": name, "meanMinutes": params[0] / 60, "stdMinutes": std / 60,
                "minMinutes": params[2] / 60, "maxMinutes": params[3] / 60}

    def period(self, value: Any, path: str) -> dict[str, str]:
        row = self.object(value, path)
        self.keys(row, ("from", "to", "beginTime", "endTime"), path)
        from_day = self.string(row.get("from"), f"{path}.from")
        to_day = self.string(row.get("to"), f"{path}.to")
        if not _DAY.match(from_day) or not _DAY.match(to_day):
            raise ProsimosImportError(f"{path}: giorno non valido.")
        begin = self.string(row.get("beginTime"), f"{path}.beginTime")
        end = self.string(row.get("endTime"), f"{path}.endTime")
        if not _TIME.match(begin) or not _TIME.match(end):
            raise ProsimosImportError(f"{path}: orario non valido.")
        return {"from_day": from_day, "to_day": to_day, "begin": _millis(begin), "end": _millis(end)}


def _millis(time: str) -> str:
    """``23:59:59.999000`` (SIMOD) diventa ``23:59:59.999``: la bozza tiene i millisecondi."""
    head, dot, fraction = time.partition(".")
    return f"{head}.{fraction[:3]}" if dot else time


def is_pass_through_gateway(row: Any) -> bool:
    """Un solo percorso con probabilita' 1: nessuna scelta da simulare."""
    probabilities = row.get("probabilities") if isinstance(row, dict) else None
    if not isinstance(probabilities, list) or len(probabilities) != 1 or not isinstance(probabilities[0], dict):
        return False
    try:
        return abs(float(probabilities[0].get("value")) - 1) <= PROBABILITY_TOLERANCE
    except (TypeError, ValueError):
        return False


def _same_periods(a: list[dict[str, str]], b: list[dict[str, str]]) -> bool:
    def normalized(periods: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{**item, "begin": _TRAILING_ZERO_SECONDS.sub("", item["begin"]),
                 "end": _TRAILING_ZERO_SECONDS.sub("", item["end"])} for item in periods]
    return normalized(a) == normalized(b)


def _not_empty(value: Any) -> bool:
    return value is not None and not (isinstance(value, (list, dict, str)) and len(value) == 0)


def import_prosimos_json(
    value: Any,
    current: dict[str, Any] | None,
    template: ScenarioTemplateResponse | None,
    mapping: dict[str, dict[str, str]] | None = None,
) -> ProsimosImport:
    """La bozza che il pannello ricava da uno scenario Prosimos, con gli avvisi."""
    if template is None:
        raise ProsimosImportError("Il modello BPMN deve essere caricato prima di importare un JSON Prosimos.")
    reader = _Reader()
    source = reader.object(value, "scenario")
    mapping = mapping or {}

    for key, item in source.items():
        if key in CORE_SECTIONS or key in METADATA_SECTIONS:
            continue
        if _not_empty(item):
            reader.warn("notImported", key)

    base = copy.deepcopy(current) if current is not None else copy.deepcopy(DEFAULT_SCENARIO)

    calendars = []
    for index, entry in enumerate(reader.list(source.get("resource_calendars"), "resource_calendars")):
        path = f"resource_calendars[{index}]"
        row = reader.object(entry, path)
        reader.keys(row, ("id", "name", "time_periods"), path)
        calendars.append({
            "id": reader.string(row.get("id"), f"{path}.id"),
            "name": reader.string(row.get("name"), f"{path}.name"),
            "periods": [reader.period(item, f"{path}.time_periods[{i}]")
                        for i, item in enumerate(reader.list(row.get("time_periods"), f"{path}.time_periods"))],
        })
    standard_id = template.standard_calendar.id if template.standard_calendar else None
    custom_calendars = [calendar for calendar in calendars if calendar["id"] != standard_id]
    custom_ids = {calendar["id"] for calendar in custom_calendars}

    profiles = reader.list(source.get("resource_profiles"), "resource_profiles")
    if not profiles:
        raise ProsimosImportError("resource_profiles: almeno un profilo risorsa richiesto.")
    resources: list[dict[str, Any]] = []
    for profile_index, entry in enumerate(profiles):
        path = f"resource_profiles[{profile_index}]"
        profile = reader.object(entry, path)
        reader.keys(profile, ("id", "name", "resource_list"), path)
        reader.string(profile.get("id"), f"{path}.id")
        reader.string(profile.get("name"), f"{path}.name")
        for index, item in enumerate(reader.list(profile.get("resource_list"), f"{path}.resource_list")):
            resource_path = f"{path}.resource_list[{index}]"
            row = reader.object(item, resource_path)
            reader.keys(row, ("id", "name", "cost_per_hour", "amount", "calendar", "assignedTasks"), resource_path)
            calendar_id = None if row.get("calendar") is None else reader.string(row.get("calendar"), f"{resource_path}.calendar")
            if calendar_id and calendar_id != standard_id and calendar_id not in custom_ids:
                raise ProsimosImportError(f"Calendario risorsa non trovato: {calendar_id}.")
            resource = {
                "id": reader.string(row.get("id"), f"{resource_path}.id"),
                "name": reader.string(row.get("name"), f"{resource_path}.name"),
                "costPerHour": reader.number(row.get("cost_per_hour"), f"{resource_path}.cost_per_hour"),
                "amount": reader.number(row.get("amount"), f"{resource_path}.amount"),
                "parametersConfirmed": True,
            }
            if calendar_id and calendar_id != standard_id:
                resource["calendarId"] = calendar_id
            resources.append(resource)
    resource_ids = {resource["id"] for resource in resources}
    if len(resource_ids) != len(resources):
        raise ProsimosImportError("Identificativi risorsa duplicati tra i profili: assegnazione ambigua.")

    task_ids = [task.element_id for task in template.tasks]
    known_tasks = set(task_ids)
    tasks: dict[str, Any] = {}
    for index, item in enumerate(reader.list(source.get("task_resource_distribution"), "task_resource_distribution")):
        path = f"task_resource_distribution[{index}]"
        row = reader.object(item, path)
        reader.keys(row, ("task_id", "resources"), path)
        source_id = reader.string(row.get("task_id"), f"{path}.task_id")
        element_id = (mapping.get("tasks") or {}).get(source_id) or source_id
        if element_id not in known_tasks:
            raise ProsimosImportError(f"Attività non presente nel BPMN: {element_id}.")
        if element_id in tasks:
            raise ProsimosImportError(f"Attività {element_id} assegnata da più elementi del JSON.")
        assignments = []
        for i, entry in enumerate(reader.list(row.get("resources"), f"{path}.resources")):
            assignment_path = f"{path}.resources[{i}]"
            assignment = reader.object(entry, assignment_path)
            reader.keys(assignment, ("resource_id", "distribution_name", "distribution_params"), assignment_path)
            resource_id = reader.string(assignment.get("resource_id"), f"{assignment_path}.resource_id")
            if resource_id not in resource_ids:
                raise ProsimosImportError(f"Risorsa non trovata per {element_id}: {resource_id}.")
            assignments.append({"resourceId": resource_id, **reader.duration(
                {"distribution_name": assignment.get("distribution_name"),
                 "distribution_params": assignment.get("distribution_params")}, assignment_path)})
        if not assignments:
            raise ProsimosImportError(f"{element_id}: nessuna risorsa assegnata.")
        primary, *others = assignments
        tasks[element_id] = {**primary, "assignmentSource": "manual", **({"otherAssignments": others} if others else {})}
    missing_tasks = [element_id for element_id in task_ids if element_id not in tasks]
    if missing_tasks:
        raise ProsimosImportError(f"Attività senza durata nel JSON: {', '.join(missing_tasks)}.")

    gateway_flows = {gateway.element_id: [branch.flow_id for branch in gateway.branches] for gateway in template.gateways}
    gateways: dict[str, dict[str, float]] = {}
    for index, item in enumerate(reader.list(source.get("gateway_branching_probabilities"), "gateway_branching_probabilities")):
        path = f"gateway_branching_probabilities[{index}]"
        row = reader.object(item, path)
        reader.keys(row, ("gateway_id", "probabilities"), path)
        source_id = reader.string(row.get("gateway_id"), f"{path}.gateway_id")
        element_id = (mapping.get("gateways") or {}).get(source_id) or source_id
        flows = gateway_flows.get(element_id)
        if flows is None and is_pass_through_gateway(row):
            reader.warn("ignoredGateway", source_id)
            continue
        if flows is None:
            raise ProsimosImportError(f"Decisione non presente nel BPMN: {element_id}.")
        if element_id in gateways:
            raise ProsimosImportError(f"Decisione {element_id} assegnata da più elementi del JSON.")
        shares: dict[str, float] = {}
        for i, branch in enumerate(reader.list(row.get("probabilities"), f"{path}.probabilities")):
            branch_path = f"{path}.probabilities[{i}]"
            probability = reader.object(branch, branch_path)
            reader.keys(probability, ("path_id", "value"), branch_path)
            source_flow = reader.string(probability.get("path_id"), f"{branch_path}.path_id")
            flow_id = (mapping.get("flows") or {}).get(flow_mapping_key(source_id, source_flow)) or source_flow
            if flow_id not in flows:
                raise ProsimosImportError(f"Flusso non presente nel BPMN: {flow_id}.")
            if flow_id in shares:
                raise ProsimosImportError(f"Flusso {flow_id} assegnato da più percorsi del JSON.")
            shares[flow_id] = reader.number(probability.get("value"), f"{branch_path}.value")
        missing_flows = [flow_id for flow_id in flows if flow_id not in shares]
        if missing_flows:
            raise ProsimosImportError(f"Flussi senza probabilità per {element_id}: {', '.join(missing_flows)}.")
        if any(share < 0 for share in shares.values()):
            raise ProsimosImportError(f"Le probabilità di {element_id} non possono essere negative.")
        total = sum(shares.values())
        if total <= 0:
            raise ProsimosImportError(f"Le probabilità di {element_id} sommano a zero.")
        if abs(total - 1) > PROBABILITY_TOLERANCE:
            reader.warn("normalizedProbabilities", element_id)
            shares = {flow_id: share / total for flow_id, share in shares.items()}
        gateways[element_id] = {flow_id: share * 100 for flow_id, share in shares.items()}

    arrival = reader.duration(source.get("arrival_time_distribution"), "arrival_time_distribution")

    template_waits = {wait.element_id: wait for wait in template.waits or []}
    waits: dict[str, Any] = {}
    for index, item in enumerate(reader.list(source.get("event_distribution") or [], "event_distribution")):
        path = f"event_distribution[{index}]"
        row = reader.object(item, path)
        reader.keys(row, ("event_id", "distribution_name", "distribution_params"), path)
        source_id = reader.string(row.get("event_id"), f"{path}.event_id")
        element_id = (mapping.get("waits") or {}).get(source_id) or source_id
        template_wait = template_waits.get(element_id)
        if template_wait is None:
            raise ProsimosImportError(f"{path}: evento {element_id} non presente tra le attese del BPMN corrente.")
        if element_id in waits:
            raise ProsimosImportError(f"{path}: evento {element_id} duplicato.")
        parsed = reader.duration({"distribution_name": row.get("distribution_name"),
                                  "distribution_params": row.get("distribution_params")}, path)
        # Prosimos rappresenta un'attesa di messaggio non impostata come durata fissa zero.
        if parsed["distribution"] == "fixed" and parsed["meanMinutes"] == 0:
            if template_wait.kind == "timer":
                raise ProsimosImportError(f"{path}: il timer {element_id} ha durata zero; non può sostituire la durata del BPMN.")
            continue
        waits[element_id] = parsed

    arrival_periods = [reader.period(entry, f"arrival_time_calendar[{index}]")
                       for index, entry in enumerate(reader.list(source.get("arrival_time_calendar"), "arrival_time_calendar"))]
    arrival_calendar_id = None
    standard_periods = [period.model_dump() for period in template.standard_calendar.periods] if template.standard_calendar else []
    if not _same_periods(arrival_periods, standard_periods):
        match = next((calendar for calendar in custom_calendars if _same_periods(calendar["periods"], arrival_periods)), None)
        if match is not None:
            arrival_calendar_id = match["id"]
        else:
            if ARRIVAL_CALENDAR_ID in custom_ids:
                raise ProsimosImportError("Identificativo calendario arrivi già utilizzato.")
            arrival_calendar_id = ARRIVAL_CALENDAR_ID
            custom_calendars.append({"id": ARRIVAL_CALENDAR_ID, "name": "Arrivi importati", "periods": arrival_periods})

    arrival_draft: dict[str, Any] = {"distribution": arrival["distribution"]}
    for key in ("stdMinutes", "minMinutes", "maxMinutes"):
        if key in arrival:
            arrival_draft[key] = arrival[key]
    if arrival_calendar_id is not None:
        arrival_draft["calendarId"] = arrival_calendar_id
    draft = {
        **base, "resources": resources, "tasks": tasks, "gateways": gateways, "waits": waits,
        "calendars": custom_calendars, "arrivalIntervalMinutes": arrival["meanMinutes"], "arrival": arrival_draft,
    }
    return ProsimosImport(draft=draft, warnings=reader.warnings)
