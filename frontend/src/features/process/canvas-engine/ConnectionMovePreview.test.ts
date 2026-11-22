import { describe, expect, it } from "vitest";
import { movedConnectionWaypoints } from "./ConnectionMovePreview";
import { businessObject, type CanvasElement } from "./types";

const shape = (id: string, x: number): CanvasElement => ({ id, type: "bpmn:Task", businessObject: businessObject("bpmn:Task", { id }), x, y: 0, width: 100, height: 80 });

describe("moving connection preview", () => {
  it("keeps the arrow attached while one endpoint moves", () => {
    const source = shape("source", 0), target = shape("target", 250);
    const edge: CanvasElement = { id: "flow", type: "bpmn:SequenceFlow", businessObject: businessObject("bpmn:SequenceFlow", { id: "flow" }), x: 0, y: 0, width: 0, height: 0, source, target, waypoints: [{ x: 100, y: 40 }, { x: 250, y: 40 }] };
    const before = JSON.stringify(edge.waypoints);
    const route = movedConnectionWaypoints(edge, { x: 30, y: 25 }, true, false);
    expect(route[0]).not.toEqual(edge.waypoints?.[0]);
    expect(route.at(-1)?.x).toBe(target.x);
    expect(route.at(-1)?.y).toBeGreaterThanOrEqual(target.y);
    expect(route.at(-1)?.y).toBeLessThanOrEqual(target.y + target.height);
    expect(JSON.stringify(edge.waypoints)).toBe(before);
  });
  it("translates a connection when both endpoints move together", () => {
    const source = shape("source", 0), target = shape("target", 250);
    const edge: CanvasElement = { id: "flow", type: "bpmn:SequenceFlow", businessObject: businessObject("bpmn:SequenceFlow", { id: "flow" }), x: 0, y: 0, width: 0, height: 0, source, target, waypoints: [{ x: 100, y: 40 }, { x: 250, y: 40 }] };
    expect(movedConnectionWaypoints(edge, { x: 30, y: 25 }, true, true)).toEqual([{ x: 130, y: 65 }, { x: 280, y: 65 }]);
  });
});
