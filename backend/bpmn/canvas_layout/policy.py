"""Product-owned geometry. Agent tool schemas never expose these parameters."""
from dataclasses import dataclass

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"

FLOW_TYPES = frozenset({
    "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
    "boundaryEvent", "task", "userTask", "serviceTask", "sendTask", "receiveTask",
    "manualTask", "businessRuleTask", "scriptTask", "subProcess", "callActivity",
    "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
    "complexGateway",
})
ARTIFACT_TYPES = frozenset({"dataObjectReference", "dataStoreReference", "textAnnotation"})


@dataclass(frozen=True)
class CanvasLayoutPolicy:
    version: str = "delir-lr-v1"
    origin_x: float = 80
    origin_y: float = 80
    pool_label_width: float = 30
    lane_label_width: float = 30
    padding: float = 40
    column_gap: float = 80
    row_gap: float = 150
    task_width: float = 160
    task_height: float = 80
    event_size: float = 36
    gateway_size: float = 50
    route_clearance: float = 12
    bend_cost: float = 24
    crossing_cost: float = 100


ENTERPRISE_POLICY = CanvasLayoutPolicy()


def local_name(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def tag(name: str) -> str:
    return f"{{{BPMN}}}{name}"
