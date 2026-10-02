"""Geometry regressions for dense, multi-lane BPMN drafts."""

import xml.etree.ElementTree as ET
from pathlib import Path

from backend.bpmn import semantic_model_to_bpmn_xml
from backend.bpmn.models import (
    BPMNFlowNode,
    BPMNMessageFlow,
    BPMNParticipant,
    BPMNSemanticModel,
    BPMNSequenceFlow,
)
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

    assert layout_bpmn_di(laid_out) == laid_out
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
    assert float(waypoints[0].attrib["y"]) < float(waypoints[1].attrib["y"])


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


def test_purchase_layout_keeps_lanes_inside_company_pool_and_separates_connectors():
    xml = Path("tests/fixtures/purchase_layout.bpmn").read_text(encoding="utf-8")
    laid_out = layout_bpmn_di(xml)
    shapes = _bounds(laid_out)
    report = validate_bpmn_layout(laid_out)

    assert layout_bpmn_di(laid_out) == laid_out
    assert report["valid"] is True
    assert report["warnings"] == []
    assert report["metrics"]["edge_edge_crossing_count"] == 0
    assert report["metrics"]["edge_shape_crossing_count"] == 0
    assert report["metrics"]["bounds"]["height"] < 1100
    company = shapes["Company"]
    supplier = shapes["Supplier"]
    assert supplier["x"] == company["x"]
    assert supplier["width"] == company["width"]
    assert supplier["y"] + supplier["height"] < company["y"]
    for lane_id in ("Technical", "Purchasing", "Maintenance"):
        lane = shapes[lane_id]
        assert lane["x"] == company["x"] + 30
        assert lane["x"] + lane["width"] == company["x"] + company["width"]
    assert shapes["Technical"]["y"] == company["y"]
    assert shapes["Maintenance"]["y"] + shapes["Maintenance"]["height"] == company["y"] + company["height"]
    assert shapes["Technical"]["y"] + shapes["Technical"]["height"] == shapes["Purchasing"]["y"]
    assert shapes["Purchasing"]["y"] + shapes["Purchasing"]["height"] == shapes["Maintenance"]["y"]
    assert shapes["Purchasing"]["y"] < shapes["End"]["y"] < shapes["Maintenance"]["y"]

    root = ET.fromstring(laid_out)
    urgent_edge = next(
        edge for edge in root.iter(f"{{{BPMNDI_NS}}}BPMNEdge")
        if edge.attrib.get("bpmnElement") == "F8"
    )
    assert urgent_edge.find(f"{{{BPMNDI_NS}}}BPMNLabel") is None
    bpmn_ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"
    elements = {element.attrib["id"]: element for element in root.iter()
                if element.tag.startswith(f"{{{bpmn_ns}}}") and element.attrib.get("id")}
    for flow_id in ("F3", "F8", "Supplier_Message"):
        flow = elements[flow_id]
        assert "name" not in flow.attrib
        assert flow.find(f"{{{bpmn_ns}}}documentation") is not None
    for flow_id in ("F4", "F5"):
        assert elements[flow_id].attrib.get("name")

    for node_id in ("Decision", "End"):
        node_shape = next(
            shape for shape in root.iter(f"{{{BPMNDI_NS}}}BPMNShape")
            if shape.attrib.get("bpmnElement") == node_id
        )
        assert node_shape.find(f"{{{BPMNDI_NS}}}BPMNLabel/{{{DC_NS}}}Bounds") is not None


def test_compiler_order_branch_and_boundary_event_do_not_cross_main_path():
    xml = Path("tests/fixtures/purchase_layout.bpmn").read_text(encoding="utf-8")
    director = '<bpmn:userTask id="Director_Sign" name="Raccogli firma direttore" />'
    xml = xml.replace(f"    {director}\n", "")
    xml = xml.replace(
        '    <bpmn:endEvent id="End" name="Ordine inviato" />',
        f'    <bpmn:endEvent id="End" name="Ordine inviato" />\n    {director}',
    )
    xml = xml.replace(
        '    <bpmn:dataObjectReference id="Request_Document"',
        '    <bpmn:boundaryEvent id="Urgency_Boundary" attachedToRef="Open_Request" />\n'
        '    <bpmn:dataObjectReference id="Request_Document"',
    )
    xml = xml.replace('id="F8" name="Urgenza" sourceRef="Open_Request"',
                      'id="F8" name="Urgenza" sourceRef="Urgency_Boundary"')

    laid_out = layout_bpmn_di(xml)
    report = validate_bpmn_layout(laid_out)
    shapes = _bounds(laid_out)
    assert report["valid"] is True
    assert report["warnings"] == []
    assert shapes["Director_Sign"]["x"] < shapes["Create_Order"]["x"] < shapes["End"]["x"]


def test_long_single_lane_snakes_without_crossing_and_is_idempotent():
    nodes = "".join(
        f'<bpmn:task id="Task_{index}" name="Verifica e approva passaggio {index + 1}" />'
        for index in range(14)
    )
    refs = "".join(f'<bpmn:flowNodeRef>Task_{index}</bpmn:flowNodeRef>' for index in range(14))
    flows = "".join(
        f'<bpmn:sequenceFlow id="Flow_{index}" sourceRef="Task_{index - 1}" targetRef="Task_{index}" />'
        for index in range(1, 14)
    )
    xml = f'''<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Long">
      <bpmn:process id="Process"><bpmn:laneSet><bpmn:lane id="Lane">{refs}</bpmn:lane></bpmn:laneSet>
      {nodes}{flows}</bpmn:process></bpmn:definitions>'''
    first = layout_bpmn_di(xml)
    second = layout_bpmn_di(first)
    report = validate_bpmn_layout(first)
    shapes = _bounds(first)

    assert first == second
    assert report["valid"] is True
    assert report["warnings"] == []
    assert shapes["Task_5"]["x"] == shapes["Task_6"]["x"]
    assert shapes["Task_6"]["x"] > shapes["Task_7"]["x"]
    assert shapes["Task_11"]["x"] == shapes["Task_12"]["x"]


def test_repeated_branches_across_lanes_remain_unentangled_and_idempotent():
    xml = Path("tests/fixtures/multibranch_layout.bpmn").read_text(encoding="utf-8")
    first = layout_bpmn_di(xml)
    second = layout_bpmn_di(first)
    report = validate_bpmn_layout(first)

    assert first == second
    assert report["valid"] is True
    assert report["warnings"] == []
    assert report["metrics"]["edge_edge_crossing_count"] == 0
    assert report["metrics"]["edge_shape_crossing_count"] == 0


def test_serializer_shows_connector_text_only_on_gateway_branches():
    model = BPMNSemanticModel(
        id="Process_Labels", name="Etichette dei collegamenti",
        flowNodes=[
            BPMNFlowNode(id="Start", type="startEvent", name="Avvio"),
            BPMNFlowNode(id="Decision", type="exclusiveGateway", name="Approvata?"),
            BPMNFlowNode(id="Work", type="task", name="Prepara ordine"),
            BPMNFlowNode(id="End", type="endEvent", name="Concluso"),
        ],
        sequenceFlows=[
            BPMNSequenceFlow(id="First", sourceRef="Start", targetRef="Decision", name="Richiesta ricevuta"),
            BPMNSequenceFlow(id="Branch", sourceRef="Decision", targetRef="Work", name="Sì"),
            BPMNSequenceFlow(id="Last", sourceRef="Work", targetRef="End", name="Ordine pronto"),
        ],
        participants=[
            BPMNParticipant(id="Company", name="Azienda", processRef="Process_Labels"),
            BPMNParticipant(id="Supplier", name="Fornitore", isExternal=True),
        ],
        messageFlows=[
            BPMNMessageFlow(id="Message", sourceRef="Supplier", targetRef="Work", name="Conferma"),
        ],
    )
    xml = semantic_model_to_bpmn_xml(model)
    root = ET.fromstring(xml)
    elements = {element.attrib["id"]: element for element in root.iter() if element.attrib.get("id")}
    model_ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"

    assert elements["Branch"].attrib["name"] == "Sì"
    for flow_id in ("First", "Last", "Message"):
        assert "name" not in elements[flow_id].attrib
        assert elements[flow_id].find(f"{{{model_ns}}}documentation") is not None
