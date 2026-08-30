from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.models import BpmnGateway, BpmnTask, ProsimosScenario


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


def build_prosimos_scenario(
    *,
    bpmn_xml: str,
    request: CreateSimulationRunRequest,
) -> ProsimosScenario:
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    if not tasks:
        raise ValueError("Il BPMN non contiene task simulabili.")

    calendar_id = "delir-calendar-standard"
    resource_id = "delir-resource-operator"
    profile_id = "delir-profile-operator"
    task_ids = [task.id for task in tasks]
    duration = float(request.default_task_duration_seconds)
    duration_std = max(1.0, duration * 0.1)
    # Prosimos / pix-framework requires norm distributions as
    # [mean, std, min, max]; min/max bound the rejection sampling loop.
    duration_min = max(0.0, duration - 3.0 * duration_std)
    duration_max = duration + 3.0 * duration_std

    arrival_mean = max(1.0, float(request.arrival_interval_seconds))

    payload = {
        "resource_profiles": [
            {
                "id": profile_id,
                "name": request.resource_name.strip() or "Operatore",
                "resource_list": [
                    {
                        "id": resource_id,
                        "name": request.resource_name.strip() or "Operatore",
                        "cost_per_hour": str(float(request.default_cost_per_hour)),
                        "amount": int(request.resource_amount),
                        "calendar": calendar_id,
                        "assignedTasks": task_ids,
                    }
                ],
            }
        ],
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
            _equal_gateway_probability(gateway) for gateway in gateways
        ],
        "task_resource_distribution": [
            {
                "task_id": task.id,
                "resources": [
                    {
                        "resource_id": resource_id,
                        "distribution_name": "norm",
                        "distribution_params": [
                            {"value": duration},
                            {"value": duration_std},
                            {"value": duration_min},
                            {"value": duration_max},
                        ],
                    }
                ],
            }
            for task in tasks
        ],
        "resource_calendars": [
            {
                "id": calendar_id,
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


def parse_bpmn_for_simulation(bpmn_xml: str) -> tuple[list[BpmnTask], list[BpmnGateway]]:
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc

    tasks: list[BpmnTask] = []
    gateway_ids: set[str] = set()
    outgoing_by_source: dict[str, list[str]] = defaultdict(list)

    for element in root.iter():
        tag = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue

        if tag in TASK_TYPES:
            tasks.append(BpmnTask(id=element_id, name=element.attrib.get("name") or element_id))
        elif tag in BRANCHING_GATEWAY_TYPES:
            gateway_ids.add(element_id)
        elif tag == "sequenceFlow":
            source_ref = element.attrib.get("sourceRef")
            if source_ref:
                outgoing_by_source[source_ref].append(element_id)

    gateways = [
        BpmnGateway(id=gateway_id, outgoing_flow_ids=tuple(flow_ids))
        for gateway_id, flow_ids in outgoing_by_source.items()
        if gateway_id in gateway_ids and len(flow_ids) > 1
    ]

    return tasks, gateways


def _equal_gateway_probability(gateway: BpmnGateway) -> dict:
    probability = 1 / len(gateway.outgoing_flow_ids)
    return {
        "gateway_id": gateway.id,
        "probabilities": [
            {"path_id": flow_id, "value": str(probability)}
            for flow_id in gateway.outgoing_flow_ids
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
