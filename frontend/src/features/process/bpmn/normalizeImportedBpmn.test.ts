import { describe, expect, it } from "vitest";

import { BpmnDocument } from "../canvas-engine/BpmnDocument";
import { NS } from "../canvas-engine/types";
import { normalizeImportedBpmn } from "./normalizeImportedBpmn";

const foreign = `<bpmn:definitions xmlns:bpmn="${NS.bpmn}" xmlns:bpmndi="${NS.bpmndi}" xmlns:dc="${NS.dc}" xmlns:di="${NS.di}" xmlns:vendor="urn:vendor">
  <bpmn:process id="P"><bpmn:startEvent id="Start"/><bpmn:task id="Work" name="Create Request for Quotation Requester Manager" vendor:flag="keep"/><bpmn:endEvent id="End"/>
    <bpmn:sequenceFlow id="F1" sourceRef="Start" targetRef="Work"/><bpmn:sequenceFlow id="F2" sourceRef="Work" targetRef="End"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="D"><bpmndi:BPMNPlane id="Plane" bpmnElement="P">
    <bpmndi:BPMNShape id="S_di" bpmnElement="Start"><dc:Bounds x="20" y="52" width="25" height="25"/></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="W_di" bpmnElement="Work"><dc:Bounds x="90" y="45" width="100" height="40"/></bpmndi:BPMNShape>
    <bpmndi:BPMNShape id="E_di" bpmnElement="End"><dc:Bounds x="240" y="52" width="25" height="25"/></bpmndi:BPMNShape>
    <bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="45" y="65"/><di:waypoint x="90" y="65"/></bpmndi:BPMNEdge>
    <bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="190" y="65"/><di:waypoint x="240" y="65"/></bpmndi:BPMNEdge>
  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
</bpmn:definitions>`;

describe("foreign BPMN geometry", () => {
  it("uses DeliR-sized editable elements while preserving IDs and vendor data", () => {
    const normalized = normalizeImportedBpmn(foreign);
    const document = new BpmnDocument(normalized);
    const work = document.records.find((record) => record.id === "Work")!;
    expect(work).toMatchObject({ type: "bpmn:Task", width: 160, height: 88 });
    expect(work.businessObject.name).toBe("Create Request for Quotation Requester Manager");
    expect(document.records.find((record) => record.id === "F1")?.targetId).toBe("Work");
    expect(document.records.find((record) => record.id === "F1")?.waypoints?.at(-1)?.x).toBe(work.x);
    expect(document.records.find((record) => record.id === "F2")?.waypoints?.[0]?.x).toBe(work.x + work.width);
    expect(document.document.getElementById("Work")?.getAttributeNS("urn:vendor", "flag")).toBe("keep");
    expect(normalizeImportedBpmn(normalized)).toBe(normalized);
  });

  it("keeps a native DeliR layout and its original XML intact", () => {
    const native = foreign.replace('x="90" y="45" width="100" height="40"', 'x="90" y="45" width="160" height="88"');
    expect(normalizeImportedBpmn(native)).toBe(native);
  });
});
