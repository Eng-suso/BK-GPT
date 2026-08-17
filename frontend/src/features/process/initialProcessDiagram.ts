function xmlText(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export function buildInitialProcessDiagram(processName: string) {
  const name = xmlText(processName || "Processo");

  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Process_Workspace" targetNamespace="https://workspace.local/bpmn">
  <bpmn:process id="Process_Workspace" name="${name}" isExecutable="false">
    <bpmn:startEvent id="StartEvent_Input" name="Input">
      <bpmn:outgoing>Flow_Input_To_Collect</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:userTask id="Task_Collect_Data" name="Raccolta dati">
      <bpmn:incoming>Flow_Input_To_Collect</bpmn:incoming>
      <bpmn:outgoing>Flow_Collect_To_Validate</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_Validate" name="Validazione">
      <bpmn:incoming>Flow_Collect_To_Validate</bpmn:incoming>
      <bpmn:outgoing>Flow_Validate_To_Decision</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="Gateway_Decision" name="Decisione">
      <bpmn:incoming>Flow_Validate_To_Decision</bpmn:incoming>
      <bpmn:outgoing>Flow_Decision_To_Output</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:endEvent id="EndEvent_Output" name="Output">
      <bpmn:incoming>Flow_Decision_To_Output</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_Input_To_Collect" sourceRef="StartEvent_Input" targetRef="Task_Collect_Data" />
    <bpmn:sequenceFlow id="Flow_Collect_To_Validate" sourceRef="Task_Collect_Data" targetRef="Task_Validate" />
    <bpmn:sequenceFlow id="Flow_Validate_To_Decision" sourceRef="Task_Validate" targetRef="Gateway_Decision" />
    <bpmn:sequenceFlow id="Flow_Decision_To_Output" sourceRef="Gateway_Decision" targetRef="EndEvent_Output" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_Process_Workspace">
    <bpmndi:BPMNPlane id="BPMNPlane_Process_Workspace" bpmnElement="Process_Workspace">
      <bpmndi:BPMNShape id="StartEvent_Input_di" bpmnElement="StartEvent_Input">
        <dc:Bounds x="130" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_Collect_Data_di" bpmnElement="Task_Collect_Data">
        <dc:Bounds x="230" y="138" width="140" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_Validate_di" bpmnElement="Task_Validate">
        <dc:Bounds x="430" y="138" width="140" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Gateway_Decision_di" bpmnElement="Gateway_Decision" isMarkerVisible="true">
        <dc:Bounds x="640" y="153" width="50" height="50" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_Output_di" bpmnElement="EndEvent_Output">
        <dc:Bounds x="770" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_Input_To_Collect_di" bpmnElement="Flow_Input_To_Collect">
        <di:waypoint x="166" y="178" />
        <di:waypoint x="230" y="178" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_Collect_To_Validate_di" bpmnElement="Flow_Collect_To_Validate">
        <di:waypoint x="370" y="178" />
        <di:waypoint x="430" y="178" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_Validate_To_Decision_di" bpmnElement="Flow_Validate_To_Decision">
        <di:waypoint x="570" y="178" />
        <di:waypoint x="640" y="178" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_Decision_To_Output_di" bpmnElement="Flow_Decision_To_Output">
        <di:waypoint x="690" y="178" />
        <di:waypoint x="770" y="178" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;
}
