"""Geometry regressions for dense, multi-lane BPMN drafts."""

import xml.etree.ElementTree as ET

from backend.workspace_services.bpmn_canvas_edit import (
    BPMNDI_NS,
    BpmnLayoutConfig,
    DC_NS,
    DI_NS,
    layout_bpmn_di,
    validate_bpmn_layout,
)


def _bounds(xml: str) -> dict[str, dict[str, float]]:
    root = ET.fromstring(xml)
    result = {}
    for shape in root.iter(f"{{{BPMNDI_NS}}}BPMNShape"):
        bounds = shape.find(f"{{{DC_NS}}}Bounds")
        if bounds is not None:
            result[shape.attrib["bpmnElement"]] = {
                key: float(bounds.attrib[key]) for key in ("x", "y", "width", "height")
            }
    return result


def test_dense_lanes_use_only_the_rows_they_contain():
    nodes = "\n".join(
        f'<bpmn:userTask id="Task_{index}" name="Attivita {index}" />'
        for index in range(12)
    )
    lanes = "\n".join(
        f'<bpmn:lane id="Lane_{lane}"><bpmn:flowNodeRef>'
        + "</bpmn:flowNodeRef><bpmn:flowNodeRef>".join(
            f"Task_{index}" for index in indexes
        )
        + "</bpmn:flowNodeRef></bpmn:lane>"
        for lane, indexes in (("A", range(5)), ("B", range(5, 10)), ("C", range(10, 12)))
    )
    xml = f"""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
      xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
      xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
      xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
      <bpmn:collaboration id="Collaboration_Test">
        <bpmn:participant id="Company" processRef="Process_Test" />
        <bpmn:participant id="Supplier" />
        <bpmn:messageFlow id="Supplier_Message" sourceRef="Supplier" targetRef="Task_0" />
      </bpmn:collaboration>
      <bpmn:process id="Process_Test">
        <bpmn:laneSet id="Lanes">{lanes}</bpmn:laneSet>
        {nodes}
        <bpmn:dataObjectReference id="Document" name="Richiesta" />
        <bpmn:association id="Data_Out" sourceRef="Task_0" targetRef="Document" />
      </bpmn:process>
    </bpmn:definitions>"""

    laid_out = layout_bpmn_di(xml)
    shapes = _bounds(laid_out)
    report = validate_bpmn_layout(laid_out)

    assert report["valid"] is True
    assert report["metrics"]["bounds"]["height"] < 1200
    assert shapes["Lane_A"]["height"] == shapes["Lane_B"]["height"]
    assert shapes["Lane_C"]["height"] == shapes["Lane_A"]["height"]
    assert shapes["Lane_A"]["y"] <= shapes["Document"]["y"]
    assert (shapes["Document"]["y"] + shapes["Document"]["height"]
            <= shapes["Lane_A"]["y"] + shapes["Lane_A"]["height"])
    assert shapes["Lane_A"]["y"] + shapes["Lane_A"]["height"] == shapes["Lane_B"]["y"]
    root = ET.fromstring(laid_out)
    message_edge = next(
        edge for edge in root.iter(f"{{{BPMNDI_NS}}}BPMNEdge")
        if edge.attrib.get("bpmnElement") == "Supplier_Message"
    )
    waypoints = list(message_edge.iter(f"{{{DI_NS}}}waypoint"))
    assert float(waypoints[0].attrib["x"]) == float(waypoints[1].attrib["x"])


def test_layout_report_identifies_connectors_through_other_activities():
    xml = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
      xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
      xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
      xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
      <bpmn:process id="Process_Test">
        <bpmn:task id="A" /><bpmn:task id="B" /><bpmn:task id="C" />
        <bpmn:sequenceFlow id="Flow_AC" sourceRef="A" targetRef="C" />
      </bpmn:process>
      <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test">
        <bpmndi:BPMNShape id="A_di" bpmnElement="A"><dc:Bounds x="100" y="100" width="100" height="80" /></bpmndi:BPMNShape>
        <bpmndi:BPMNShape id="B_di" bpmnElement="B"><dc:Bounds x="300" y="100" width="100" height="80" /></bpmndi:BPMNShape>
        <bpmndi:BPMNShape id="C_di" bpmnElement="C"><dc:Bounds x="500" y="100" width="100" height="80" /></bpmndi:BPMNShape>
        <bpmndi:BPMNEdge id="Flow_AC_di" bpmnElement="Flow_AC">
          <di:waypoint x="200" y="140" /><di:waypoint x="500" y="140" />
        </bpmndi:BPMNEdge>
      </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
    </bpmn:definitions>"""

    report = validate_bpmn_layout(xml)

    assert report["metrics"]["edge_shape_crossing_count"] == 1
    assert any("attraversano" in warning for warning in report["warnings"])


def test_wide_layout_plan_wraps_before_nodes_leave_the_lane():
    tasks = "".join(f'<bpmn:task id="Task_{index}" />' for index in range(6))
    refs = "".join(f'<bpmn:flowNodeRef>Task_{index}</bpmn:flowNodeRef>' for index in range(6))
    xml = f"""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
      xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
      xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
      xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
      <bpmn:process id="Process_Test">
        <bpmn:laneSet id="Lanes"><bpmn:lane id="Lane_A">{refs}</bpmn:lane></bpmn:laneSet>
        {tasks}
      </bpmn:process>
    </bpmn:definitions>"""

    laid_out = layout_bpmn_di(
        xml, config=BpmnLayoutConfig(max_nodes_per_row=6, column_gap=390)
    )
    shapes = _bounds(laid_out)
    lane_right = shapes["Lane_A"]["x"] + shapes["Lane_A"]["width"]

    assert shapes["Lane_A"]["width"] <= 1900
    assert all(
        shapes[f"Task_{index}"]["x"] + shapes[f"Task_{index}"]["width"] < lane_right
        for index in range(6)
    )
