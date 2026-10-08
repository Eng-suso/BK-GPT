from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    ScenarioTemplateBranch,
    ScenarioTemplateGateway,
    ScenarioTemplateResponse,
    ScenarioTemplateTask,
    SimCalendarConfig,
    SimCalendarPeriodConfig,
)
from backend.simulation.bpmn_resources import describe_bpmn_resources
from backend.simulation.ir import compile_for_prosimos, model_from_request
from backend.simulation.ir.baseline import baseline_model
from backend.simulation.ir.bpmn_check import check_model_against_bpmn
from backend.simulation.ir.from_request import standard_calendar
from backend.simulation.ir.model import SimulationModel
from backend.simulation.ir.patch import apply_patch
from backend.simulation.models import BpmnFlow, BpmnGateway, BpmnTask, ProsimosScenario
from backend.simulation.validation import validate_simulation_bpmn


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
    """Lo scenario Prosimos della richiesta, passando dal Simulation IR.

    La richiesta diventa un modello esplicito (`model_from_request`), il modello
    diventa lo scenario del motore (`compile_for_prosimos`). Il JSON e' lo
    stesso del builder storico: lo garantiscono gli scenari golden nei test.

    Una ``model_patch`` porta cio' che i campi v1 non esprimono (attributi del
    caso, rami per regola): si applica al modello tradotto, che poi si verifica
    di nuovo sul BPMN, perche' la patch puo' nominare elementi che non ci sono.
    """
    validate_simulation_bpmn(bpmn_xml)
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    model = model_from_request(request, tasks, gateways)
    if request.model_patch:
        model = apply_patch(model, request.model_patch)
        check_model_against_bpmn(model, tasks, gateways)
    return ProsimosScenario(
        payload=compile_for_prosimos(model),
        task_count=len(tasks),
        gateway_count=len(gateways),
        model=model.model_dump(mode="json"),
    )


def baseline_for_bpmn(bpmn_xml: str, *, source_bpmn_xml: str | None = None) -> SimulationModel:
    """L'IR di partenza del BPMN normalizzato, con le risorse dei suoi pool e lane.

    ``source_bpmn_xml`` e' il BPMN prima della normalizzazione: pool e lane si
    leggono da li', come fa il template della configurazione.
    """
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    resources = describe_bpmn_resources(source_bpmn_xml or bpmn_xml, {task.id for task in tasks})
    return baseline_model(tasks, gateways, resources)


def build_prosimos_scenario_from_model(*, bpmn_xml: str, model: SimulationModel) -> ProsimosScenario:
    """Lo scenario Prosimos di un IR dato, dopo aver verificato che parli del BPMN."""
    validate_simulation_bpmn(bpmn_xml)
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    check_model_against_bpmn(model, tasks, gateways)
    return ProsimosScenario(
        payload=compile_for_prosimos(model),
        task_count=len(tasks),
        gateway_count=len(gateways),
        model=model.model_dump(mode="json"),
    )


def describe_scenario_template(bpmn_xml: str, *, source_bpmn_xml: str | None = None) -> ScenarioTemplateResponse:
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    return ScenarioTemplateResponse(
        resources=describe_bpmn_resources(source_bpmn_xml or bpmn_xml, {task.id for task in tasks}),
        tasks=[
            ScenarioTemplateTask(element_id=task.id, name=task.name, type=task.type)
            for task in tasks
        ],
        standard_calendar=_standard_calendar_config(),
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


def _standard_calendar_config() -> SimCalendarConfig:
    calendar = standard_calendar()
    return SimCalendarConfig(
        id=calendar.id,
        name=calendar.name,
        periods=[
            SimCalendarPeriodConfig(from_day=p.from_day, to_day=p.to_day, begin=p.begin[:5], end=p.end[:5])
            for p in calendar.periods
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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
