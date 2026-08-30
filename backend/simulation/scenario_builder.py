from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    ScenarioTemplateBranch,
    ScenarioTemplateGateway,
    ScenarioTemplateResponse,
    ScenarioTemplateTask,
)
from backend.simulation.models import BpmnFlow, BpmnGateway, BpmnTask, ProsimosScenario


TASK_TYPES = {
    "task",
    "userTask",
    "serviceTask",
    "scriptTask",
    "businessRuleTask",
    "manualTask",
    "sendTask",
    "receiveTask",
    "callActivity",
}

BRANCHING_GATEWAY_TYPES = {
    "exclusiveGateway",
    "inclusiveGateway",
}

_DEFAULT_CALENDAR_ID = "delir-calendar-standard"
_DEFAULT_RESOURCE_ID = "delir-resource-operator"
_DEFAULT_PROFILE_ID = "delir-profile-operator"


def build_prosimos_scenario(
    *,
    bpmn_xml: str,
    request: CreateSimulationRunRequest,
) -> ProsimosScenario:
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    if not tasks:
        raise ValueError("Il BPMN non contiene task simulabili.")

    resources = _resource_profiles(request, tasks)
    resource_ids = {r["id"] for pool in resources for r in pool["resource_list"]}
    default_resource_id = next(iter(resource_ids), _DEFAULT_RESOURCE_ID)
    task_overrides = {cfg.element_id: cfg for cfg in (request.tasks or [])}
    gateway_overrides = {cfg.element_id: cfg for cfg in (request.gateways or [])}

    arrival_mean = max(1.0, float(request.arrival_interval_seconds))

    payload = {
        "resource_profiles": resources,
        "arrival_time_distribution": {
            # pix-framework expon contract: [mean, min(loc), max]. scale = mean - min.
            "distribution_name": "expon",
            "distribution_params": [
                {"value": arrival_mean},
                {"value": 0.0},
                {"value": arrival_mean * 10.0},
            ],
        },
        "arrival_time_calendar": [_standard_week_calendar()],
        "gateway_branching_probabilities": [
            _gateway_probability(gateway, gateway_overrides.get(gateway.id))
            for gateway in gateways
        ],
        "task_resource_distribution": [
            _task_distribution(
                task=task,
                override=task_overrides.get(task.id),
                default_seconds=float(request.default_task_duration_seconds),
                default_resource_id=default_resource_id,
                resource_ids=resource_ids,
            )
            for task in tasks
        ],
        "resource_calendars": [
            {
                "id": _DEFAULT_CALENDAR_ID,
                "name": "Standard office calendar",
                "time_periods": [_standard_week_calendar()],
            }
        ],
        "batch_processing": [],
        "case_attributes": [],
    }

    return ProsimosScenario(
        payload=payload,
        task_count=len(tasks),
        gateway_count=len(gateways),
    )


def describe_scenario_template(bpmn_xml: str) -> ScenarioTemplateResponse:
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    return ScenarioTemplateResponse(
        tasks=[
            ScenarioTemplateTask(element_id=task.id, name=task.name, type=task.type)
            for task in tasks
        ],
        gateways=[
            ScenarioTemplateGateway(
                element_id=gateway.id,
                name=gateway.name or gateway.id,
                type=gateway.type,
                branches=[
                    ScenarioTemplateBranch(
                        flow_id=flow.id,
                        flow_name=flow.name,
                        target_name=flow.target_name,
                    )
                    for flow in gateway.outgoing_flows
                ],
            )
            for gateway in gateways
        ],
    )


# --- BPMN parsing -----------------------------------------------------------


def parse_bpmn_for_simulation(bpmn_xml: str) -> tuple[list[BpmnTask], list[BpmnGateway]]:
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc

    tasks: list[BpmnTask] = []
    names_by_id: dict[str, str] = {}
    gateway_types: dict[str, str] = {}
    gateway_names: dict[str, str] = {}
    flows: list[tuple[str, str, str, str]] = []  # (id, name, source, target)

    for element in root.iter():
        tag = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        name = element.attrib.get("name") or ""
        if name:
            names_by_id[element_id] = name

        if tag in TASK_TYPES:
            tasks.append(BpmnTask(id=element_id, name=name or element_id, type=tag))
        elif tag in BRANCHING_GATEWAY_TYPES:
            gateway_types[element_id] = tag
            gateway_names[element_id] = name
        elif tag == "sequenceFlow":
            source = element.attrib.get("sourceRef") or ""
            target = element.attrib.get("targetRef") or ""
            flows.append((element_id, name, source, target))

    outgoing_by_source: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for flow_id, flow_name, source, target in flows:
        if source:
            outgoing_by_source[source].append((flow_id, flow_name, target))

    gateways: list[BpmnGateway] = []
    for gateway_id, gateway_type in gateway_types.items():
        outgoing = outgoing_by_source.get(gateway_id, [])
        if len(outgoing) <= 1:
            continue
        gateways.append(
            BpmnGateway(
                id=gateway_id,
                name=gateway_names.get(gateway_id, ""),
                type=gateway_type,
                outgoing_flows=tuple(
                    BpmnFlow(
                        id=flow_id,
                        name=flow_name,
                        target_name=names_by_id.get(target, ""),
                    )
                    for flow_id, flow_name, target in outgoing
                ),
            )
        )

    return tasks, gateways


# --- scenario assembly helpers -------------------------------------------------


def _resource_profiles(
    request: CreateSimulationRunRequest,
    tasks: list[BpmnTask],
) -> list[dict]:
    task_ids = [task.id for task in tasks]
    task_overrides = {cfg.element_id: cfg for cfg in (request.tasks or [])}

    if request.resources:
        resource_list = []
        for cfg in request.resources:
            assigned = [
                task.id
                for task in tasks
                if (task_overrides.get(task.id) and task_overrides[task.id].resource_id == cfg.id)
            ]
            resource_list.append(
                {
                    "id": cfg.id,
                    "name": cfg.name,
                    "cost_per_hour": str(float(cfg.cost_per_hour)),
                    "amount": int(cfg.amount),
                    "calendar": _DEFAULT_CALENDAR_ID,
                    "assignedTasks": assigned,
                }
            )
        # Any task not explicitly assigned falls to the first resource.
        assigned_all = {tid for r in resource_list for tid in r["assignedTasks"]}
        leftover = [tid for tid in task_ids if tid not in assigned_all]
        if leftover and resource_list:
            resource_list[0]["assignedTasks"] = list(
                dict.fromkeys(resource_list[0]["assignedTasks"] + leftover)
            )
        return [{"id": _DEFAULT_PROFILE_ID, "name": "Risorse", "resource_list": resource_list}]

    name = request.resource_name.strip() or "Operatore"
    return [
        {
            "id": _DEFAULT_PROFILE_ID,
            "name": name,
            "resource_list": [
                {
                    "id": _DEFAULT_RESOURCE_ID,
                    "name": name,
                    "cost_per_hour": str(float(request.default_cost_per_hour)),
                    "amount": int(request.resource_amount),
                    "calendar": _DEFAULT_CALENDAR_ID,
                    "assignedTasks": task_ids,
                }
            ],
        }
    ]


def _task_distribution(
    *,
    task: BpmnTask,
    override,
    default_seconds: float,
    default_resource_id: str,
    resource_ids: set[str],
) -> dict:
    mean = float(override.mean_seconds) if override else default_seconds
    distribution = override.distribution if override else "norm"
    resource_id = (
        override.resource_id
        if override and override.resource_id in resource_ids
        else default_resource_id
    )
    return {
        "task_id": task.id,
        "resources": [
            {
                "resource_id": resource_id,
                **_duration_params(distribution, mean),
            }
        ],
    }


def _duration_params(distribution: str, mean: float) -> dict:
    mean = max(1.0, mean)
    if distribution == "fixed":
        # pix-framework "fix": single param.
        return {
            "distribution_name": "fix",
            "distribution_params": [{"value": mean}],
        }
    if distribution == "expon":
        return {
            "distribution_name": "expon",
            "distribution_params": [
                {"value": mean},
                {"value": 0.0},
                {"value": mean * 10.0},
            ],
        }
    std = max(1.0, mean * 0.1)
    return {
        "distribution_name": "norm",
        "distribution_params": [
            {"value": mean},
            {"value": std},
            {"value": max(0.0, mean - 3.0 * std)},
            {"value": mean + 3.0 * std},
        ],
    }


def _gateway_probability(gateway: BpmnGateway, override) -> dict:
    flow_ids = [flow.id for flow in gateway.outgoing_flows]
    if override and override.branches:
        by_flow = {b.flow_id: float(b.probability) for b in override.branches}
        raw = [max(0.0, by_flow.get(flow_id, 0.0)) for flow_id in flow_ids]
        total = sum(raw)
        values = (
            [value / total for value in raw]
            if total > 0
            else [1 / len(flow_ids)] * len(flow_ids)
        )
    else:
        values = [1 / len(flow_ids)] * len(flow_ids)

    return {
        "gateway_id": gateway.id,
        "probabilities": [
            {"path_id": flow_id, "value": str(value)}
            for flow_id, value in zip(flow_ids, values)
        ],
    }


def _standard_week_calendar() -> dict:
    return {
        "from": "MONDAY",
        "to": "FRIDAY",
        "beginTime": "09:00:00.000",
        "endTime": "17:00:00.000",
    }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
