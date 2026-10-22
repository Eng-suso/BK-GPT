from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree

from backend.schemas.simulation import (
    CreateSimulationRunRequest,
    ScenarioTemplateBranch,
    ScenarioTemplateEscalation,
    ScenarioTemplateGateway,
    ScenarioTemplateResponse,
    ScenarioTemplateTask,
    ScenarioTemplateWait,
    SimCalendarConfig,
    SimCalendarPeriodConfig,
)
from backend.simulation.bpmn_resources import describe_bpmn_resources
from backend.simulation.ir import compile_for_prosimos, model_from_request
from backend.simulation.ir.escalations import expand_escalations
from backend.simulation.ir.flow_rules import expand_flow_rules
from backend.simulation.ir.instances import expand_instances
from backend.simulation.ir.from_request import with_band_attribute, with_flow_rules, with_request_waits
from backend.simulation.ir.variants import expand_duration_variants
from backend.simulation.ir.waits import with_bpmn_waits
from backend.simulation.ir.baseline import baseline_model
from backend.simulation.ir.bpmn_check import check_model_against_bpmn
from backend.simulation.ir.from_request import standard_calendar
from backend.simulation.ir.model import SimulationModel, TimerEscalation
from backend.simulation.ir.patch import apply_patch
from backend.simulation.models import BpmnFlow, BpmnGateway, BpmnTask, BpmnWait, ProsimosScenario
from backend.simulation.timers import (
    ESCALATION_AFTER,
    ESCALATION_INTERRUPTING,
    ESCALATION_NORMAL_FLOW,
    ESCALATION_OF,
    INSTANCES,
    INSTANCES_SEQUENTIAL,
    TIMER_OF,
    duration_seconds,
)
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
    model = with_band_attribute(model, request)
    model = with_flow_rules(model, request)
    model = with_bpmn_waits(with_request_waits(model, request), parse_bpmn_waits(bpmn_xml))
    return _scenario(bpmn_xml, model, tasks, gateways)


def _scenario(bpmn_xml: str, model: SimulationModel, tasks: list[BpmnTask], gateways: list[BpmnGateway]) -> ProsimosScenario:
    """Il payload del motore, con escalation a tempo, salti e rilavorazioni
    (SIM-35) e durate condizionali (SIM-32) compilati in decisioni.

    Il run conserva il modello come l'ha scritto il consulente, non le varianti:
    l'inspector mostra le durate per categoria sull'attivita' vera. I salti
    vengono prima: una variante di durata sta dentro il salto, non attorno.
    """
    engine_bpmn, engine_model = expand_instances(bpmn_xml, model)
    engine_bpmn, engine_model = expand_escalations(engine_bpmn, engine_model)
    engine_bpmn, engine_model = expand_flow_rules(engine_bpmn, engine_model)
    engine_bpmn, engine_model = expand_duration_variants(engine_bpmn, engine_model)
    return ProsimosScenario(
        payload=compile_for_prosimos(engine_model),
        task_count=len(tasks),
        gateway_count=len(gateways),
        model=model.model_dump(mode="json"),
        bpmn_xml=engine_bpmn if engine_bpmn is not bpmn_xml else None,
    )


def baseline_for_bpmn(bpmn_xml: str, *, source_bpmn_xml: str | None = None) -> SimulationModel:
    """L'IR di partenza del BPMN normalizzato, con le risorse dei suoi pool e lane.

    ``source_bpmn_xml`` e' il BPMN prima della normalizzazione: pool e lane si
    leggono da li', come fa il template della configurazione.
    """
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    resources = describe_bpmn_resources(source_bpmn_xml or bpmn_xml, {task.id for task in tasks})
    return with_bpmn_waits(baseline_model(tasks, gateways, resources), parse_bpmn_waits(bpmn_xml))


def build_prosimos_scenario_from_model(*, bpmn_xml: str, model: SimulationModel) -> ProsimosScenario:
    """Lo scenario Prosimos di un IR dato, dopo aver verificato che parli del BPMN."""
    validate_simulation_bpmn(bpmn_xml)
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    check_model_against_bpmn(model, tasks, gateways)
    model = with_bpmn_waits(model, parse_bpmn_waits(bpmn_xml))
    return _scenario(bpmn_xml, model, tasks, gateways)


def describe_scenario_template(bpmn_xml: str, *, source_bpmn_xml: str | None = None) -> ScenarioTemplateResponse:
    tasks, gateways = parse_bpmn_for_simulation(bpmn_xml)
    return ScenarioTemplateResponse(
        waits=[
            ScenarioTemplateWait(element_id=wait.id, name=wait.name or wait.id, kind=wait.kind, seconds=wait.seconds)
            for wait in parse_bpmn_waits(bpmn_xml)
            if not wait.internal
        ],
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
                escalation=(
                    ScenarioTemplateEscalation(**gateway.escalation.model_dump()) if gateway.escalation else None
                ),
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


def parse_bpmn_waits(bpmn_xml: str) -> list[BpmnWait]:
    """SIM-11c/d: gli eventi intermedi rimasti nel BPMN normalizzato, che il caso aspetta."""
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc
    kinds = {"timerEventDefinition": "timer", "messageEventDefinition": "message",
             "signalEventDefinition": "signal", "conditionalEventDefinition": "conditional"}
    waits = []
    for element in root.iter():
        if _local_name(element.tag) != "intermediateCatchEvent" or not element.attrib.get("id"):
            continue
        definitions = [child for child in element if _local_name(child.tag) in kinds]
        if len(definitions) != 1:
            continue
        kind = kinds[_local_name(definitions[0].tag)]
        seconds = None
        if kind == "timer":
            text = next((c.text for c in definitions[0] if _local_name(c.tag) == "timeDuration"), None)
            seconds = duration_seconds(text)
            if seconds is None:
                continue
        waits.append(BpmnWait(id=element.attrib["id"], name=element.attrib.get("name") or "", kind=kind, seconds=seconds,
                              internal=bool(element.attrib.get(TIMER_OF))))
    return waits


def parse_bpmn_for_simulation(bpmn_xml: str) -> tuple[list[BpmnTask], list[BpmnGateway]]:
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc

    tasks: list[BpmnTask] = []
    names_by_id: dict[str, str] = {}
    gateway_types: dict[str, str] = {}
    gateway_names: dict[str, str] = {}
    escalations: dict[str, TimerEscalation] = {}
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
            tasks.append(BpmnTask(
                id=element_id, name=name or element_id, type=tag,
                instances=int(element.attrib.get(INSTANCES, "1")),
                sequential_instances=element.attrib.get(INSTANCES_SEQUENTIAL, "true") == "true",
            ))
        elif tag in BRANCHING_GATEWAY_TYPES:
            gateway_types[element_id] = tag
            gateway_names[element_id] = name
            if element.attrib.get(ESCALATION_OF):
                escalations[element_id] = TimerEscalation(
                    activity_id=element.attrib[ESCALATION_OF],
                    after_seconds=float(element.attrib.get(ESCALATION_AFTER, "0")),
                    normal_flow_id=element.attrib.get(ESCALATION_NORMAL_FLOW, ""),
                    interrupting=element.attrib.get(ESCALATION_INTERRUPTING) != "false",
                )
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
                escalation=escalations.get(gateway_id),
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
