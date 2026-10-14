"""Readable routing: the main path runs left to right, lane handovers are vertical,
a rework loop that passes through another lane stays next to its decision.
"""
import xml.etree.ElementTree as ET

from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model

BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"
DI = "{http://www.omg.org/spec/DD/20100524/DI}"

# Requester above purchasing above manager. "Complete?" sends incomplete
# requests back to the requester (rework through another lane) and complete
# ones down to the manager.
PURCHASE = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs" targetNamespace="http://delir.local/tests">
  <bpmn:process id="Purchase" isExecutable="false">
    <bpmn:laneSet id="Lanes">
      <bpmn:lane id="Requester"><bpmn:flowNodeRef>Start</bpmn:flowNodeRef><bpmn:flowNodeRef>Send</bpmn:flowNodeRef><bpmn:flowNodeRef>Fix</bpmn:flowNodeRef></bpmn:lane>
      <bpmn:lane id="Purchasing"><bpmn:flowNodeRef>Check</bpmn:flowNodeRef><bpmn:flowNodeRef>Complete</bpmn:flowNodeRef><bpmn:flowNodeRef>Ask</bpmn:flowNodeRef></bpmn:lane>
      <bpmn:lane id="Manager"><bpmn:flowNodeRef>Approve</bpmn:flowNodeRef><bpmn:flowNodeRef>End</bpmn:flowNodeRef></bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="Start" />
    <bpmn:userTask id="Send" name="Send the request" />
    <bpmn:userTask id="Check" name="Check the request" />
    <bpmn:exclusiveGateway id="Complete" name="Request complete?" default="No" />
    <bpmn:userTask id="Ask" name="Ask for the missing data" />
    <bpmn:userTask id="Fix" name="Complete the request" />
    <bpmn:userTask id="Approve" name="Approve the spend" />
    <bpmn:endEvent id="End" />
    <bpmn:sequenceFlow id="F1" sourceRef="Start" targetRef="Send" />
    <bpmn:sequenceFlow id="F2" sourceRef="Send" targetRef="Check" />
    <bpmn:sequenceFlow id="F3" sourceRef="Check" targetRef="Complete" />
    <bpmn:sequenceFlow id="Yes" name="Yes" sourceRef="Complete" targetRef="Approve"><bpmn:conditionExpression>complete</bpmn:conditionExpression></bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="No" name="No" sourceRef="Complete" targetRef="Ask" />
    <bpmn:sequenceFlow id="F4" sourceRef="Ask" targetRef="Fix" />
    <bpmn:sequenceFlow id="Back" sourceRef="Fix" targetRef="Check" />
    <bpmn:sequenceFlow id="F5" sourceRef="Approve" targetRef="End" />
  </bpmn:process>
</bpmn:definitions>"""


def _layout():
    root = ET.fromstring(apply_enterprise_layout(PURCHASE))
    shapes = {
        shape.get("bpmnElement"): {key: float(value) for key, value in shape.find(f"{DC}Bounds").attrib.items()}
        for shape in root.iter(f"{BPMNDI}BPMNShape")
    }
    edges = {
        edge.get("bpmnElement"): [(float(p.get("x")), float(p.get("y"))) for p in edge.findall(f"{DI}waypoint")]
        for edge in root.iter(f"{BPMNDI}BPMNEdge")
    }
    return root, shapes, edges


def _cx(box):
    return box["x"] + box["width"] / 2


def test_rework_through_another_lane_stays_next_to_its_decision():
    _, shapes, edges = _layout()
    # The rework stacks in the decision's own column...
    assert _cx(shapes["Complete"]) == _cx(shapes["Ask"]) == _cx(shapes["Fix"])
    # ...above the decision, on the side of the lane it goes back to,
    assert shapes["Ask"]["y"] < shapes["Complete"]["y"]
    # so the way back to "Check" is one short corner, not a lap of the diagram.
    assert len(edges["Back"]) <= 3
    assert all(_cx(shapes["Check"]) <= x <= _cx(shapes["Fix"]) for x, _ in edges["Back"])


def test_the_decision_hands_over_to_the_lane_below_with_one_vertical():
    _, shapes, edges = _layout()
    assert _cx(shapes["Approve"]) == _cx(shapes["Complete"])
    assert len({x for x, _ in edges["Yes"]}) == 1


def test_no_flow_crosses_or_overlaps_another():
    root, _, _ = _layout()
    report = lint_visual_model(root)
    assert report["valid"] and report["metrics"]["edge_crossings"] == 0 and report["warnings"] == []


def test_an_exclusive_gateway_declares_its_x_marker():
    """Ogni visualizzatore disegna la X: bpmn-js la mostra solo se il DI la dichiara."""
    root = ET.fromstring(apply_enterprise_layout(PURCHASE))

    shape = next(s for s in root.iter(f"{BPMNDI}BPMNShape") if s.get("bpmnElement") == "Complete")
    assert shape.get("isMarkerVisible") == "true"
    assert all(s.get("isMarkerVisible") is None for s in root.iter(f"{BPMNDI}BPMNShape") if s.get("bpmnElement") != "Complete")
