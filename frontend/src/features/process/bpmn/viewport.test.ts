import { describe, expect, it } from "vitest";

import { getDiagramBounds, hasDiagramContent, readableViewbox, withViewportPadding } from "./viewport";
import type { BpmnModeler, BpmnRegistryElement } from "./types";

/** A modeler whose element registry holds exactly these elements. */
function fakeModeler(elements: BpmnRegistryElement[]): BpmnModeler {
  return {
    importXML: async () => undefined,
    saveXML: async () => ({}),
    destroy: () => undefined,
    get: () => ({
      filter: (predicate: (element: BpmnRegistryElement) => boolean) =>
        elements.filter(predicate),
    }),
  };
}

describe("hasDiagramContent", () => {
  it("calls a model with only its process shell empty", () => {
    expect(
      hasDiagramContent(
        fakeModeler([
          { id: "Process_Workspace", type: "bpmn:Process" },
          { id: "__implicitroot" },
        ]),
      ),
    ).toBe(false);
  });

  it("sees a model as soon as something has been drawn on it", () => {
    expect(
      hasDiagramContent(
        fakeModeler([
          { id: "Process_Workspace", type: "bpmn:Process" },
          { id: "StartEvent_1", type: "bpmn:StartEvent" },
        ]),
      ),
    ).toBe(true);
  });
});

describe("getDiagramBounds", () => {
  it("returns null when there is nothing measurable", () => {
    expect(getDiagramBounds([])).toBeNull();
    expect(getDiagramBounds([{ id: "__implicitroot" }])).toBeNull();
  });

  it("wraps shapes and connection waypoints in one box", () => {
    const bounds = getDiagramBounds([
      { id: "a", x: 100, y: 100, width: 80, height: 60 },
      { id: "b", x: 400, y: 300, width: 100, height: 80 },
      { id: "edge", waypoints: [{ x: 180, y: 130 }, { x: 400, y: 340 }] },
    ]);

    expect(bounds).toEqual({ x: 100, y: 100, width: 400, height: 280 });
  });

  it("ignores the implicit root shape", () => {
    const bounds = getDiagramBounds([
      { id: "__implicitroot", x: -10000, y: -10000, width: 1, height: 1 },
      { id: "a", x: 0, y: 0, width: 50, height: 50 },
    ]);
    expect(bounds).toEqual({ x: 0, y: 0, width: 50, height: 50 });
  });
});

describe("withViewportPadding", () => {
  it("keeps the diagram centred inside the padded viewport ratio", () => {
    const padded = withViewportPadding(
      { x: 0, y: 0, width: 600, height: 400 },
      2, // wide viewport
    );

    // The box is widened to match the viewport ratio, centred on the source.
    expect(padded.width / padded.height).toBeCloseTo(2);
    const sourceCenterX = 300;
    expect(padded.x + padded.width / 2).toBeCloseTo(sourceCenterX);
  });

  it("enforces a minimum framed height", () => {
    const padded = withViewportPadding(
      { x: 0, y: 0, width: 20, height: 10 },
      1,
    );
    expect(padded.height).toBeGreaterThanOrEqual(420);
  });
});

describe("readableViewbox", () => {
  const bounds = { x: 110, y: 160, width: 1828, height: 870 };
  const start = { x: 298, y: 264, width: 36, height: 36, type: "bpmn:StartEvent" };

  it("keeps a fit overview on a large desktop viewport", () => {
    const view = readableViewbox(bounds, { width: 2200, height: 1100 }, start);
    expect(view.width).toBeGreaterThan(bounds.width);
    expect(view.x).toBeLessThan(bounds.x);
  });

  it("holds a legible scale and shows the first step in a narrow pane", () => {
    const outer = { width: 1000, height: 600 };
    const view = readableViewbox(bounds, outer, start);
    expect(outer.width / view.width).toBeCloseTo(1);
    expect(start.x).toBeGreaterThan(view.x);
    expect(start.x).toBeLessThan(view.x + view.width);
  });

  it("starts at normal text scale on a phone", () => {
    const outer = { width: 390, height: 844 };
    const view = readableViewbox(bounds, outer, start);
    expect(outer.width / view.width).toBeCloseTo(1);
    expect(start.x).toBeGreaterThan(view.x);
    expect(start.x + start.width).toBeLessThan(view.x + view.width);
  });
});
