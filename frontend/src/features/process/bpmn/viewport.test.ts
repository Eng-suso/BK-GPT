import { describe, expect, it } from "vitest";

import { getDiagramBounds, withViewportPadding } from "./viewport";

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
