"""La richiesta di run che il pannello costruisce da una bozza del workspace.

Il run di uno scenario del workspace cita scenario e revisioni (SIM-14), ma i
parametri li porta la richiesta, costruita dal browser. Qui il server rifa' la
stessa traduzione dalla bozza salvata, per verificare che il run simuli cio'
che il workspace dice: una scheda con modifiche non salvate, o una chiamata a
mano, non possono far passare per "scenario A" un'altra cosa.

La traduzione e' quella di ``simulationScenario.ts`` (``parseScenarioDraft`` →
``seedDraftFromTemplate`` → ``scenarioToInput``) e di ``runRequestBody`` in
``simulationApi.ts``, con i moduli che usano (``caseRules``, ``flowRules``,
``slaSegments``, ``arrivalBands``). I casi di
``tests/fixtures/simulation/draft_request_cases.json`` valgono per entrambe:
cambiando una delle due, il test dell'altra fallisce.

Le bozze sono JSON: un campo assente in TypeScript e' ``undefined``, che qui e'
la chiave mancante; ``null`` resta ``None``. Gli arrotondamenti seguono
``Math.round``.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from backend.schemas.simulation import ScenarioTemplateResponse

WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
DISTRIBUTION_PARAMETERS: dict[str, dict[str, bool]] = {
    "fixed": {"mean": True, "std": False, "bounds": False},
    "expon": {"mean": True, "std": False, "bounds": True},
    "uniform": {"mean": False, "std": False, "bounds": True},
    "norm": {"mean": True, "std": True, "bounds": True},
    "lognorm": {"mean": True, "std": True, "bounds": True},
    "gamma": {"mean": True, "std": True, "bounds": True},
}
DEFAULT_SCENARIO: dict[str, Any] = {
    "scenarioName": "Baseline AS-IS",
    "totalCases": 100,
    "arrivalIntervalMinutes": 30,
    "defaultTaskMinutes": 15,
    "resources": [],
    "tasks": {},
    "gateways": {},
}
RULE_OPERATORS = (">", ">=", "<", "<=", "=", "!=")
MAX_SLA_SEGMENTS = 20
MAX_BANDS = 21
MAX_WINDOWS = 21
BAND_ATTRIBUTE_NAME = "fascia_arrivo"
PROVENANCE = {"origin": "manual"}


class DraftTranslationError(ValueError):
    """La bozza salvata non si traduce: il pannello non avrebbe potuto avviarla."""


# --- aritmetica di JavaScript -------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value)


def _num(value: Any) -> float:
    """``value`` come lo usa l'aritmetica di JavaScript: ``null`` vale 0."""
    if value is None:
        return 0
    if _is_number(value):
        return value
    raise DraftTranslationError("La bozza ha un valore non numerico dove serve un numero.")


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def _truthy(value: Any) -> bool:
    """La verita' di JavaScript per i valori di una bozza JSON."""
    if value is None or value is False:
        return False
    if _is_number(value):
        return value != 0 and not math.isnan(value)
    if isinstance(value, str):
        return value != ""
    return True


def _obj(value: Any) -> bool:
    return isinstance(value, dict)


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    """Le chiavi ``undefined`` (qui ``...``) spariscono, come in ``JSON.stringify``."""
    return {key: item for key, item in value.items() if item is not ...}


# --- parseScenarioDraft e sanitizzazione ---------------------------------------


def _is_rule(rule: Any) -> bool:
    return (
        _obj(rule)
        and isinstance(rule.get("attributeId"), str)
        and isinstance(rule.get("value"), str)
        and rule.get("operator") in RULE_OPERATORS
    )


def _is_groups(groups: Any) -> bool:
    return isinstance(groups, list) and all(isinstance(group, list) and all(_is_rule(rule) for rule in group) for group in groups)


def _sanitize_attributes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    def keep(attribute: Any) -> bool:
        if not _obj(attribute) or not isinstance(attribute.get("id"), str) or not isinstance(attribute.get("name"), str):
            return False
        if attribute.get("kind") == "number":
            return _is_number(attribute.get("minimum")) and _is_number(attribute.get("maximum"))
        categories = attribute.get("categories")
        return (
            attribute.get("kind") == "category"
            and isinstance(categories, list)
            and all(_obj(c) and isinstance(c.get("value"), str) and _is_number(c.get("percent")) for c in categories)
        )

    return [attribute for attribute in raw if keep(attribute)]


def _sanitize_priorities(raw: Any) -> list[Any]:
    return [groups for groups in raw if _is_groups(groups)] if isinstance(raw, list) else []


def _sanitize_gateway_rules(raw: Any) -> dict[str, Any]:
    if not _obj(raw):
        return {}
    out: dict[str, Any] = {}
    for gateway, branches in raw.items():
        if not _obj(branches):
            continue
        out[gateway] = {flow: groups for flow, groups in branches.items() if _is_groups(groups)}
    return out


def _sanitize_skip(raw: Any) -> Any:
    if not _obj(raw) or not _is_number(raw.get("percent")):
        return ...
    return {"percent": raw["percent"], **({"rule": raw["rule"]} if _is_groups(raw.get("rule")) else {})}


def _sanitize_rework(raw: Any) -> Any:
    if not _obj(raw):
        return ...
    if not isinstance(raw.get("backTo"), str) or not _is_number(raw.get("percent")) or not _is_number(raw.get("maxRepeats")):
        return ...
    return {
        "backTo": raw["backTo"],
        "percent": raw["percent"],
        "maxRepeats": raw["maxRepeats"],
        **({"rule": raw["rule"]} if _is_groups(raw.get("rule")) else {}),
    }


def _sanitize_outcome(raw: Any) -> Any:
    if not _obj(raw) or not isinstance(raw.get("name"), str) or not isinstance(raw.get("categories"), list):
        return ...
    categories = raw["categories"]
    if not all(_obj(c) and isinstance(c.get("value"), str) and _is_number(c.get("percent")) for c in categories):
        return ...
    return {"name": raw["name"], "categories": categories}


def _sanitize_duration_windows(raw: Any) -> Any:
    if not isinstance(raw, list):
        return ...
    kept = [
        w for w in raw
        if _obj(w) and w.get("fromDay") in WEEKDAYS and w.get("toDay") in WEEKDAYS
        and isinstance(w.get("begin"), str) and isinstance(w.get("end"), str) and _is_number(w.get("percent"))
    ]
    return kept[:MAX_WINDOWS] if kept else ...


def _sanitize_tasks(raw: Any) -> dict[str, Any]:
    if not _obj(raw):
        return {}
    out: dict[str, Any] = {}
    for element_id, task in raw.items():
        if not _obj(task):
            out[element_id] = task
            continue
        clean = task
        if "skip" in task or "rework" in task:
            clean = _compact({**task, "skip": _sanitize_skip(task.get("skip")), "rework": _sanitize_rework(task.get("rework"))})
        if "outcome" in task:
            clean = _compact({**clean, "outcome": _sanitize_outcome(task.get("outcome"))})
        if "durationWindows" in task:
            clean = _compact({**clean, "durationWindows": _sanitize_duration_windows(task.get("durationWindows"))})
        out[element_id] = clean
    return out


def _sanitize_sla_segments(raw: Any) -> Any:
    if not isinstance(raw, list):
        return ...
    segments = []
    for item in raw:
        if not _obj(item) or not isinstance(item.get("attributeId"), str) or not isinstance(item.get("value"), str):
            continue
        if not _finite(item.get("target")) or not _finite(item.get("sharePercent")):
            continue
        segments.append({
            "attributeId": item["attributeId"],
            "value": item["value"],
            "target": item["target"],
            "sharePercent": item["sharePercent"],
            "unit": "hours" if item.get("unit") == "hours" else "days",
        })
    segments = segments[:MAX_SLA_SEGMENTS]
    return segments or ...


def _sanitize_sla(raw: Any) -> Any:
    if not _obj(raw) or not _finite(raw.get("target")) or not _finite(raw.get("sharePercent")):
        return ...
    segments = _sanitize_sla_segments(raw.get("segments"))
    return {
        "target": raw["target"],
        "sharePercent": raw["sharePercent"],
        "unit": "hours" if raw.get("unit") == "hours" else "days",
        **({"segments": segments} if segments is not ... else {}),
    }


def _sanitize_arrival_bands(raw: Any) -> Any:
    if not isinstance(raw, list):
        return ...
    kept = [
        band for band in raw
        if _obj(band) and band.get("fromDay") in WEEKDAYS and band.get("toDay") in WEEKDAYS
        and isinstance(band.get("begin"), str) and isinstance(band.get("end"), str) and _is_number(band.get("meanMinutes"))
    ]
    return kept[:MAX_BANDS] if kept else ...


def _sanitize_arrival(raw: Any) -> Any:
    if not _obj(raw) or not _truthy(raw.get("distribution")) or raw.get("distribution") not in DISTRIBUTION_PARAMETERS:
        return ...

    def number(value: Any) -> Any:
        return value if _finite(value) else ...

    return _compact({
        "distribution": raw["distribution"],
        "stdMinutes": number(raw.get("stdMinutes")),
        "minMinutes": number(raw.get("minMinutes")),
        "maxMinutes": number(raw.get("maxMinutes")),
        "calendarId": raw["calendarId"] if isinstance(raw.get("calendarId"), str) else ...,
        "bands": _sanitize_arrival_bands(raw.get("bands")),
        **({"bandAttribute": True} if raw.get("bandAttribute") is True else {}),
        "months": _sanitize_arrival_months(raw.get("months")),
    })


def _sanitize_arrival_months(raw: Any) -> Any:
    """``sanitizeArrivalMonths``: SIM-08b, i mesi con mese e variazione numerici."""
    if not isinstance(raw, list):
        return ...
    kept = [m for m in raw if _obj(m) and _is_number(m.get("month")) and _is_number(m.get("percent"))]
    return kept[:12] if kept else ...


def _valid_calendar(calendar: Any) -> bool:
    if not _obj(calendar) or not isinstance(calendar.get("id"), str) or not isinstance(calendar.get("name"), str):
        return False
    periods = calendar.get("periods")
    return isinstance(periods, list) and all(
        _obj(p) and p.get("from_day") in WEEKDAYS and p.get("to_day") in WEEKDAYS
        and isinstance(p.get("begin"), str) and isinstance(p.get("end"), str)
        for p in periods
    )


def _calendar(calendar: dict[str, Any]) -> dict[str, Any]:
    """Il calendario come lo restituisce zod: solo le chiavi dello schema."""
    return {
        "id": calendar["id"],
        "name": calendar["name"],
        "periods": [{key: p[key] for key in ("from_day", "to_day", "begin", "end")} for p in calendar["periods"]],
    }


def _legacy_default(resource: Any) -> bool:
    return (
        _obj(resource) and resource.get("id") == "res-1" and resource.get("name") == "Operatore"
        and resource.get("amount") == 1 and resource.get("costPerHour") == 35
        and "parametersConfirmed" not in resource and not _truthy(resource.get("source"))
    )


def parse_scenario_draft(value: Any) -> dict[str, Any]:
    """``parseScenarioDraft``: i campi mancanti prendono i default, quelli rotti si scartano."""
    if not _obj(value):
        return copy.deepcopy(DEFAULT_SCENARIO)
    resources = value.get("resources") if isinstance(value.get("resources"), list) else []
    migrated = [
        {**r, "parametersConfirmed": r.get("parametersConfirmed") if r.get("parametersConfirmed") is not None else False}
        for r in resources if not _legacy_default(r)
    ]
    horizon = value.get("horizonDays")
    return _compact({
        **copy.deepcopy(DEFAULT_SCENARIO),
        **copy.deepcopy(value),
        "resources": migrated,
        "tasks": _sanitize_tasks(value.get("tasks")),
        "gateways": value.get("gateways") if value.get("gateways") is not None else {},
        "calendars": [_calendar(c) for c in value["calendars"] if _valid_calendar(c)] if isinstance(value.get("calendars"), list) else [],
        "caseAttributes": _sanitize_attributes(value.get("caseAttributes")),
        "arrival": _sanitize_arrival(value.get("arrival")),
        "sla": _sanitize_sla(value.get("sla")),
        "horizonDays": horizon if _finite(horizon) else ...,
        "gatewayRules": _sanitize_gateway_rules(value.get("gatewayRules")),
        "casePriorities": _sanitize_priorities(value.get("casePriorities")),
    })


# --- seedDraftFromTemplate -----------------------------------------------------


def _with_valid_other_assignments(task: dict[str, Any], resource_ids: set[Any]) -> dict[str, Any]:
    if "otherAssignments" not in task:
        return task
    others = task["otherAssignments"]
    if not isinstance(others, list):
        return {key: item for key, item in task.items() if key != "otherAssignments"}
    seen = {task.get("resourceId")}
    kept = []
    for assignment in others:
        if not _obj(assignment) or assignment.get("resourceId") not in resource_ids or assignment.get("resourceId") in seen:
            continue
        seen.add(assignment.get("resourceId"))
        kept.append(assignment)
    return task if len(kept) == len(others) else {**task, "otherAssignments": kept}


def seed_draft_from_template(draft: dict[str, Any], template: ScenarioTemplateResponse) -> dict[str, Any]:
    """``seedDraftFromTemplate``: i default per gli elementi del BPMN, via quelli che non ci sono piu'."""
    candidates = template.resources
    excluded = draft.get("excludedResourceIds") or []
    resources: list[dict[str, Any]] = []
    for resource in draft["resources"]:
        source = next((c for c in candidates if c.id == resource.get("id")), None)
        if source is not None:
            stored = resource.get("source")
            stored_name = stored.get("name") if _obj(stored) else None
            name = source.name if resource.get("name") == stored_name else resource.get("name")
            resources.append({**resource, "source": source.model_dump(), "name": name})
        elif _truthy(resource.get("source")):
            resources.append({**resource, "source": None, "parametersConfirmed": False})
        else:
            resources.append(resource)
    for source in candidates:
        if not any(r.get("id") == source.id for r in resources) and source.id not in excluded:
            resources.append({"id": source.id, "name": source.name, "costPerHour": 0, "amount": 1,
                              "source": source.model_dump(), "parametersConfirmed": False})

    resource_ids = {r.get("id") for r in resources}
    tasks: dict[str, Any] = {}
    for task in template.tasks:
        model_resource_id = next(
            (c.id for c in candidates if task.element_id in c.task_ids and any(r.get("id") == c.id for r in resources)), "",
        )
        existing_task: Any = draft["tasks"].get(task.element_id)
        cfg: Any = existing_task if existing_task is not None else {
            "meanMinutes": draft.get("defaultTaskMinutes"),
            "distribution": "norm",
            "resourceId": model_resource_id,
            "assignmentSource": "bpmn",
        }
        following = cfg
        if cfg.get("assignmentSource") == "bpmn":
            following = {**cfg, "resourceId": model_resource_id}
        elif _truthy(cfg.get("resourceId")) and not any(r.get("id") == cfg.get("resourceId") for r in resources):
            following = {**cfg, "resourceId": model_resource_id, "assignmentSource": "bpmn"}
        seeded = _with_valid_other_assignments(following, resource_ids)
        # SIM-11h: le istanze per caso valgono solo dove il BPMN non le fissa.
        open_instances = task.multi_instance is not None and task.instances is None
        if "instances" in seeded and not open_instances:
            seeded = {key: value for key, value in seeded.items() if key != "instances"}
        tasks[task.element_id] = seeded

    gateways: dict[str, Any] = {}
    stored_gateways = draft.get("gateways") or {}
    for gateway in template.gateways:
        existing: Any = stored_gateways.get(gateway.element_id)
        flows = [branch.flow_id for branch in gateway.branches]
        if _obj(existing) and all(flow in existing for flow in flows):
            gateways[gateway.element_id] = {flow: existing[flow] for flow in flows}
        else:
            even = _js_round((100 / len(flows)) * 10) / 10
            gateways[gateway.element_id] = {
                flow: (100 - even * (len(flows) - 1) if index == len(flows) - 1 else even) for index, flow in enumerate(flows)
            }

    gateway_rules: dict[str, Any] = {}
    stored_rules = draft.get("gatewayRules") or {}
    for gateway in template.gateways:
        rules = stored_rules.get(gateway.element_id)
        flows = [branch.flow_id for branch in gateway.branches]
        if rules and len(flows) == len(rules) and all(flow in rules for flow in flows):
            gateway_rules[gateway.element_id] = rules

    # SIM-11d: restano le attese dei messaggi e segnali ancora nel BPMN.
    settable = {wait.element_id for wait in template.waits if wait.kind != "timer"}
    waits = {"waits": {k: v for k, v in draft["waits"].items() if k in settable}} if _truthy(draft.get("waits")) else {}

    return {**draft, "resources": resources, "tasks": tasks, "gateways": gateways, "gatewayRules": gateway_rules, **waits}


# --- scenarioToInput + runRequestBody ------------------------------------------


def _js_number(raw: str) -> float | None:
    """``Number(raw)`` per i valori che una regola accetta; ``NaN`` diventa ``null`` nel JSON."""
    if raw == "":
        return 0
    return float(raw) if re.fullmatch(r"-?\d+(?:\.\d+)?", raw) else None


def _ir_condition(groups: list[Any], attributes: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {a["id"]: a for a in attributes}
    out = []
    for group in groups:
        rules = []
        for rule in group:
            attribute = by_id.get(rule["attributeId"])
            raw = rule["value"].strip()
            value: Any = _js_number(raw.replace(",", ".", 1)) if attribute is not None and attribute["kind"] == "number" else raw
            rules.append({
                "attribute": attribute["name"].strip() if attribute is not None else rule["attributeId"],
                "operator": rule["operator"],
                "value": value,
            })
        out.append(rules)
    return {"any_of": out}


def _category_sum(attribute: dict[str, Any]) -> float:
    total: float = 0
    for category in attribute["categories"]:
        total += category["percent"] if math.isfinite(category["percent"]) else 0
    return total


def _outcome_attributes(tasks: dict[str, Any]) -> list[dict[str, Any]]:
    """``outcomeAttributes``: gli esiti delle attivita' (SIM-31b) come attributi delle regole."""
    return [
        {"id": f"outcome:{element_id}", "name": task["outcome"]["name"], "kind": "category", "categories": task["outcome"]["categories"]}
        for element_id, task in tasks.items()
        if _obj(task) and _truthy(task.get("outcome"))
    ]


def _outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    total = _category_sum(outcome) or 1
    return {
        "attribute": outcome["name"].strip(),
        "options": [{"value": c["value"].strip(), "probability": c["percent"] / total} for c in outcome["categories"]],
    }


def _model_patch(draft: dict[str, Any], rule_attributes: list[dict[str, Any]]) -> Any:
    attributes = draft.get("caseAttributes") or []
    if not attributes and not (draft.get("gatewayRules") or {}):
        return ...
    case_attributes = []
    for attribute in attributes:
        if attribute["kind"] == "number":
            case_attributes.append({
                "name": attribute["name"].strip(),
                "distribution": {"kind": "uniform", "minimum": attribute["minimum"], "maximum": attribute["maximum"]},
                "provenance": PROVENANCE,
            })
            continue
        total = _category_sum(attribute) or 1
        case_attributes.append({
            "name": attribute["name"].strip(),
            "options": [{"value": c["value"].strip(), "probability": c["percent"] / total} for c in attribute["categories"]],
            "provenance": PROVENANCE,
        })
    gateways = []
    for element_id, branches in (draft.get("gatewayRules") or {}).items():
        flows = list(branches.items())
        gateways.append({
            "element_id": element_id,
            "branches": [
                {"flow_id": flow_id, "probability": 1 / len(flows), "condition": _ir_condition(groups, rule_attributes), "provenance": PROVENANCE}
                for flow_id, groups in flows
            ],
        })
    priorities = [
        {"level": index + 1, "condition": _ir_condition(groups, rule_attributes)}
        for index, groups in enumerate(draft.get("casePriorities") or [])
    ]
    return {
        **({"case_attributes": case_attributes} if case_attributes else {}),
        **({"gateways": gateways} if gateways else {}),
        **({"priority_rules": priorities} if priorities else {}),
    }


def _parameters(distribution: Any) -> dict[str, bool]:
    parameters = DISTRIBUTION_PARAMETERS.get(distribution) if isinstance(distribution, str) else None
    if parameters is None:
        raise DraftTranslationError("La bozza ha una distribuzione che il pannello non conosce.")
    return parameters


def _seconds(duration: dict[str, Any], key: str) -> Any:
    if key not in duration:
        return ...
    return max(0, _js_round(_num(duration[key]) * 60))


def _duration(duration: dict[str, Any]) -> dict[str, Any]:
    """``durationInput`` gia' in snake_case, come la scrive ``runRequestBody``."""
    distribution = duration.get("distribution")
    parameters = _parameters(distribution)
    if distribution == "uniform" and "minMinutes" in duration and "maxMinutes" in duration:
        minutes = (_num(duration["minMinutes"]) + _num(duration["maxMinutes"])) / 2
    else:
        minutes = _num(duration.get("meanMinutes"))
    std = duration.get("stdMinutes", ...)
    return _compact({
        "mean_seconds": max(1, _js_round(minutes * 60)),
        "distribution": distribution,
        "std_seconds": max(1, _js_round(_num(std) * 60)) if parameters["std"] and std is not ... else ...,
        "min_seconds": _seconds(duration, "minMinutes") if parameters["bounds"] else ...,
        "max_seconds": _seconds(duration, "maxMinutes") if parameters["bounds"] else ...,
    })


def _duration_of(task: dict[str, Any]) -> dict[str, Any]:
    return {key: task[key] for key in ("meanMinutes", "distribution", "stdMinutes", "minMinutes", "maxMinutes") if key in task}


def _thresholds_valid(thresholds: list[Any]) -> bool:
    return len(thresholds) > 0 and all(
        _finite(t.get("upTo")) and (i == 0 or t["upTo"] > thresholds[i - 1]["upTo"]) for i, t in enumerate(thresholds)
    )


def _duration_by(task: dict[str, Any], attributes: list[dict[str, Any]]) -> Any:
    by: Any = task.get("durationBy")
    if not _truthy(by):
        return ...
    attribute = next((a for a in attributes if a["id"] == by.get("attributeId")), None)
    if attribute is None:
        return ...
    name = attribute["name"].strip()
    if attribute["kind"] == "number":
        thresholds = by.get("thresholds") or []
        if not name or not _thresholds_valid(thresholds):
            return ...
        return {"attribute": name, "variants": [{"up_to": t["upTo"], **_duration(t["duration"])} for t in thresholds]}
    values = [v for v in (c["value"].strip() for c in attribute["categories"]) if v]
    if not name or not values:
        return ...
    variants = by.get("variants") or {}
    return {
        "attribute": name,
        "variants": [
            {"value": value, **_duration(variants[value] if variants.get(value) is not None else _duration_of(task))}
            for value in values
        ],
    }


def _goal_seconds(goal: dict[str, Any]) -> int:
    return _js_round(goal["target"] * (86_400 if goal["unit"] == "days" else 3600))


def _condition_of(rule: Any, attributes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"condition": _ir_condition(rule, attributes)} if _truthy(rule) else {}


def _task(element_id: str, task: dict[str, Any], attributes: list[dict[str, Any]], rule_attributes: list[dict[str, Any]]) -> dict[str, Any]:
    if not _obj(task):
        raise DraftTranslationError("La bozza ha un'attivita' senza configurazione.")
    others = task.get("otherAssignments") or []
    skip: Any = task.get("skip")
    rework: Any = task.get("rework")
    claims = task.get("claims")
    windows = task.get("durationWindows") or []
    duration = _duration(task)
    return _compact({
        "element_id": element_id,
        "mean_seconds": duration["mean_seconds"],
        "distribution": duration["distribution"],
        "resource_id": task.get("resourceId", ...),
        "std_seconds": duration.get("std_seconds", ...),
        "min_seconds": duration.get("min_seconds", ...),
        "max_seconds": duration.get("max_seconds", ...),
        "claims": [{"claim_id": c.get("claimId"), "label": c.get("label")} for c in claims] if isinstance(claims, list) and claims else ...,
        "fixed_cost": task["fixedCost"] if _truthy(task.get("fixedCost")) else ...,
        "duration_by": _duration_by(task, attributes),
        "other_assignments": [{"resource_id": a["resourceId"], **_duration(a)} for a in others] if others else ...,
        "skip": {"probability": skip["percent"] / 100, **_condition_of(skip.get("rule"), rule_attributes)} if _truthy(skip) else ...,
        "rework": _compact({
            "back_to": rework["backTo"],
            "probability": rework["percent"] / 100,
            "max_repeats": rework["maxRepeats"],
            "condition": _ir_condition(rework["rule"], rule_attributes) if _truthy(rework.get("rule")) else ...,
        }) if _truthy(rework) else ...,
        "duration_windows": [
            {"from_day": w["fromDay"], "to_day": w["toDay"], "begin": w["begin"], "end": w["end"], "factor": 1 + w["percent"] / 100}
            for w in windows
        ] if windows else ...,
        "instances": task["instances"] if _is_number(task.get("instances")) and task["instances"] > 1 else ...,
        "outcome": _outcome(task["outcome"]) if _truthy(task.get("outcome")) else ...,
        "removable": True if _truthy(task.get("removable")) else ...,
    })


def draft_to_request_body(draft: dict[str, Any], scenario_name: str) -> dict[str, Any]:
    """``runRequestBody(scenarioToInput(draft))``, senza BPMN, chiave di idempotenza, seed e scenario."""
    resources = draft.get("resources") or []
    primary: Any = resources[0] if resources else None
    calendars = draft.get("calendars") or []
    calendar_ids = {c["id"] for c in calendars}
    attributes = draft.get("caseAttributes") or []
    # Decisioni, salti e rilavorazioni leggono anche gli esiti delle attivita' (SIM-31b).
    rule_attributes = attributes + _outcome_attributes(draft.get("tasks") or {})
    arrival: Any = draft.get("arrival")
    arrival = arrival if _obj(arrival) else {}
    arrival_calendar = arrival.get("calendarId")
    bands = arrival.get("bands") or []
    sla: Any = draft.get("sla")
    waits: Any = draft.get("waits") or {}
    replications = draft.get("replications")

    arrival_duration = _compact({
        "meanMinutes": draft.get("arrivalIntervalMinutes"),
        "distribution": arrival.get("distribution") if arrival.get("distribution") is not None else "expon",
        "stdMinutes": arrival.get("stdMinutes", ...),
        "minMinutes": arrival.get("minMinutes", ...),
        "maxMinutes": arrival.get("maxMinutes", ...),
    })
    body: dict[str, Any] = {
        "scenario_name": scenario_name,
        "total_cases": draft.get("totalCases"),
        "arrival_interval_seconds": max(1, _js_round(_num(draft.get("arrivalIntervalMinutes")) * 60)),
        "default_task_duration_seconds": max(1, _js_round(_num(draft.get("defaultTaskMinutes")) * 60)),
        "default_cost_per_hour": primary.get("costPerHour") if primary and primary.get("costPerHour") is not None else 0,
        "resource_amount": primary.get("amount") if primary and primary.get("amount") is not None else 1,
        "resource_name": primary.get("name") if primary and primary.get("name") is not None else "",
        "sla": {
            "target_seconds": _goal_seconds(sla),
            "share": sla["sharePercent"] / 100,
            **({"segments": [
                {"attribute": attribute["name"].strip(), "value": s["value"], "target_seconds": _goal_seconds(s), "share": s["sharePercent"] / 100}
                for s in sla["segments"]
                for attribute in [next((a for a in attributes if a["id"] == s["attributeId"]), None)]
                if attribute is not None
            ]} if sla.get("segments") else {}),
        } if _truthy(sla) else ...,
        "case_fixed_cost": draft["caseFixedCost"] if _truthy(draft.get("caseFixedCost")) else ...,
        "warmup_cases": draft["warmupCases"] if _truthy(draft.get("warmupCases")) else ...,
        "horizon_days": draft.get("horizonDays", ...),
        "replications": replications if _truthy(replications) and _num(replications) > 1 else ...,
        "arrival": _compact({
            **_duration(arrival_duration),
            "calendar_id": arrival_calendar if _truthy(arrival_calendar) and arrival_calendar in calendar_ids else ...,
            "bands": [
                {"from_day": b["fromDay"], "to_day": b["toDay"], "begin": b["begin"], "end": b["end"],
                 "mean_seconds": max(1, _js_round(b["meanMinutes"] * 60))}
                for b in bands
            ] if bands else ...,
            "band_attribute": BAND_ATTRIBUTE_NAME if bands and _truthy(arrival.get("bandAttribute")) else ...,
            "months": [{"month": m["month"], "factor": 1 + m["percent"] / 100} for m in arrival["months"]]
            if arrival.get("months") else ...,
        }),
        "resources": [
            _compact({
                "id": r.get("id", ...),
                "name": r.get("name", ...),
                "cost_per_hour": r.get("costPerHour", ...),
                "amount": r.get("amount", ...),
                "calendar_id": r["calendarId"] if (r.get("calendarId") or "") in calendar_ids else ...,
                "shifts": [{"amount": s.get("amount"), "calendar_id": s.get("calendarId")} for s in r["shifts"]] if r.get("shifts") else ...,
                "kind": "system" if r.get("kind") == "system" else ...,
            })
            for r in resources
        ],
        "tasks": [_task(element_id, task, attributes, rule_attributes) for element_id, task in (draft.get("tasks") or {}).items()],
        "gateways": [
            {"element_id": element_id, "branches": [
                {"flow_id": flow_id, "probability": max(0, min(1, _num(probability) / 100))} for flow_id, probability in branches.items()
            ]}
            for element_id, branches in (draft.get("gateways") or {}).items()
        ],
        "calendars": calendars if calendars else ...,
        "waits": [{"element_id": element_id, **_duration(wait)} for element_id, wait in waits.items()] if waits else ...,
        "model_patch": _model_patch(draft, rule_attributes),
    }
    return _compact(body)


def expected_request_body(stored_draft: Any, scenario_name: str, template: ScenarioTemplateResponse) -> dict[str, Any]:
    """Cio' che il pannello invia per lo scenario salvato ``stored_draft``, chiamato ``scenario_name``."""
    try:
        draft = seed_draft_from_template(parse_scenario_draft(stored_draft), template)
        return draft_to_request_body(draft, scenario_name)
    except (KeyError, TypeError, AttributeError) as exc:
        raise DraftTranslationError("La bozza salvata dello scenario non si legge: aprila nel pannello e salvala di nuovo.") from exc
