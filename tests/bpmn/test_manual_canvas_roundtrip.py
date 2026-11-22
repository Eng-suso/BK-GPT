"""Manual BPMN edits must preserve imported diagram bytes across saves."""

from backend.workspace_database.bpmn import _canvas_xml_for_write


XML = '''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="defs" targetNamespace="urn:test">
  <bpmn:process id="process"><bpmn:startEvent id="start"/><bpmn:task id="task" name="Check"/><bpmn:endEvent id="end"/><bpmn:sequenceFlow id="first" sourceRef="start" targetRef="task"/><bpmn:sequenceFlow id="last" sourceRef="task" targetRef="end"/></bpmn:process>
  <bpmndi:BPMNDiagram id="diagram"><bpmndi:BPMNPlane id="plane" bpmnElement="process">
    <bpmndi:BPMNShape id="start_di" bpmnElement="start"><dc:Bounds x="20" y="20" width="36" height="36"/></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="task_di" bpmnElement="task"><dc:Bounds x="40" y="20" width="100" height="80"/></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="end_di" bpmnElement="end"><dc:Bounds x="220" y="42" width="36" height="36"/></bpmndi:BPMNShape>
    <bpmndi:BPMNEdge id="first_di" bpmnElement="first"><di:waypoint x="56" y="38"/><di:waypoint x="40" y="38"/></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="last_di" bpmnElement="last"><di:waypoint x="140" y="60"/><di:waypoint x="220" y="60"/></bpmndi:BPMNEdge>
  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
</bpmn:definitions>'''


def test_manual_diagram_with_overlaps_saves_idempotently():
    first = _canvas_xml_for_write(XML, source="manual_save")
    second = _canvas_xml_for_write(first, source="manual_save")
    assert first == second == XML
