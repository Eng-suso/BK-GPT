import { describe, expect, it, vi } from "vitest";
import { elementKind, readCanvasElements } from "./elements";
import type { BpmnModeler } from "./types";
describe("the element navigator", () => {
  it("indexes diagram shapes once, preserving names and explicit imported colours", () => {
    const addMarker = vi.fn();
    const elements = [
      { id: "task", type: "bpmn:UserTask", x: 10, businessObject: { name: "Verify" } },
      { id: "task_label", type: "label", x: 10, labelTarget: {} },
      { id: "flow", type: "bpmn:SequenceFlow", waypoints: [] },
      { id: "root", type: "bpmn:Process" },
      { id: "custom", type: "bpmn:ServiceTask", x: 20, di: { $attrs: { "bioc:fill": "#123456" } } },
    ];
    const modeler = { get: (name: string) => name === "elementRegistry" ? { getAll: () => elements } : { addMarker, removeMarker: vi.fn() } } as unknown as BpmnModeler;
    expect(readCanvasElements(modeler)).toEqual([
      { id: "task", name: "Verify", type: "UserTask", kind: "task" },
      { id: "custom", name: "", type: "ServiceTask", kind: "automation" },
    ]);
    expect(addMarker).toHaveBeenCalledExactlyOnceWith("task", "delir-type-task");
    expect(elements[4].di?.$attrs["bioc:fill"]).toBe("#123456");
  });
  it("retains BPMN type distinctions without implying that every event is an activity", () => {
    expect(elementKind("bpmn:ExclusiveGateway")).toBe("gateway");
    expect(elementKind("bpmn:ScriptTask")).toBe("automation");
    expect(elementKind("bpmn:StartEvent")).toBe("start");
    expect(elementKind("bpmn:IntermediateCatchEvent")).toBe("other");
  });
});
