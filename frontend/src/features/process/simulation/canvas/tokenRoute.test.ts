import { describe, expect, it } from "vitest";

import type { BpmnElementRegistry, BpmnShape } from "./bpmnViewer";
import { routeBetween, spreadAlong } from "./tokenRoute";

/** start -> A -> gw -> B -> end, with gw -> A as a rework loop. */
function registry(): BpmnElementRegistry {
  const flow = (id: string, from: string, to: string, ...pts: [number, number][]): BpmnShape => ({
    id, type: "bpmn:SequenceFlow", source: { id: from }, target: { id: to }, waypoints: pts.map(([x, y]) => ({ x, y })),
  });
  const elements: BpmnShape[] = [
    { id: "start", type: "bpmn:StartEvent" },
    { id: "A", type: "bpmn:UserTask" },
    { id: "gw", type: "bpmn:ExclusiveGateway" },
    { id: "B", type: "bpmn:UserTask" },
    { id: "end", type: "bpmn:EndEvent" },
    flow("f1", "start", "A", [0, 0], [10, 0]),
    flow("f2", "A", "gw", [20, 0], [30, 0]),
    flow("f3", "gw", "B", [30, 0], [30, 10], [40, 10]),
    flow("f4", "gw", "A", [30, 0], [15, -10], [15, 0]),
    flow("f5", "B", "end", [50, 10], [60, 10]),
  ];
  return {
    get: (id: string) => elements.find((el) => el.id === id),
    filter: (fn: (el: BpmnShape) => boolean) => elements.filter(fn),
  } as BpmnElementRegistry;
}

describe("routeBetween", () => {
  it("follows the flows through the gateway between two steps", () => {
    expect(routeBetween(registry(), "A", "B")).toEqual({
      points: [{ x: 20, y: 0 }, { x: 30, y: 0 }, { x: 30, y: 10 }, { x: 40, y: 10 }],
      flows: ["f2", "f3"],
    });
  });

  it("takes the rework loop back to an earlier step", () => {
    expect(routeBetween(registry(), "A", "A")?.flows).toEqual(["f2", "f4"]);
    expect(routeBetween(registry(), "B", "A")).toBeNull(); // no path without crossing a step
  });

  it("starts at the start event and ends at the end event", () => {
    expect(routeBetween(registry(), null, "A")).toEqual({ points: [{ x: 0, y: 0 }, { x: 10, y: 0 }], flows: ["f1"] });
    expect(routeBetween(registry(), "B", null)).toEqual({ points: [{ x: 50, y: 10 }, { x: 60, y: 10 }], flows: ["f5"] });
  });
});

describe("spreadAlong", () => {
  const along = (slots: { d: number; lane: number }[]) => slots.map((s) => s.d);

  it("keeps tokens released together a gap apart, leader in front", () => {
    expect(along(spreadAlong([50, 50, 50], 100, 20))).toEqual([50, 30, 10]);
  });

  it("leaves tokens that are already apart where they are", () => {
    expect(along(spreadAlong([10, 90, 50], 100, 20))).toEqual([10, 90, 50]);
  });

  it("slides the train forward when it would start before the route", () => {
    expect(along(spreadAlong([5, 5, 5], 100, 20))).toEqual([40, 20, 0]);
  });

  it("runs in lanes beside the line when the train is longer than the route", () => {
    const slots = spreadAlong([0, 0, 0, 0, 0], 40, 20); // 3 fit per lane -> 2 lanes
    expect(slots.map((s) => s.lane).sort()).toEqual([0, 0, 0, 1, 1]);
    for (const lane of [0, 1]) {
      const ds = slots.filter((s) => s.lane === lane).map((s) => s.d).sort((a, b) => a - b);
      ds.slice(1).forEach((d, i) => expect(d - ds[i]).toBeGreaterThanOrEqual(20));
    }
  });
});
