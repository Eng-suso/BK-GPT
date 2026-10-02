import { describe, expect, it } from "vitest";
import { defaultLayout, layoutSchema } from "../dashboard/dashboardModel";
import { formatMetric } from "../dashboard/dashboardFormatting";
import { bounds, fitCamera, sceneRects, zoomCamera, resizeRect, insertionRect, freeInsertionRect } from "./canvasGeometry";

describe("analytical scene", () => {
  it("migrates legacy layouts without mutating or dropping analytical objects", () => {
    const layout = defaultLayout(), original = structuredClone(layout);
    const rects = sceneRects(layout);
    expect(Object.keys(rects)).toHaveLength(7);
    expect(layout).toEqual(original);
    expect(bounds(Object.values(rects)).height).toBeGreaterThan(rects.__process__.height);
  });
  it("round trips explicit placement and rejects invalid persisted coordinates", () => {
    const layout = defaultLayout();
    layout.groups[0].widgets[0].canvas = { x: -100, y: 90, width: 500, height: 300 };
    expect(sceneRects(layoutSchema.parse(JSON.parse(JSON.stringify(layout))))['default-0'].x).toBe(-100);
    layout.groups[0].widgets[0].canvas.x = Infinity;
    expect(layoutSchema.safeParse(layout).success).toBe(false);
  });
  it("anchors zoom to the pointer and fits an off-origin object", () => {
    const camera = { x: -120, y: 30, scale: 0.8 };
    const zoomed = zoomCamera(camera, 1.2, 300, 200);
    expect((300 - zoomed.x) / zoomed.scale).toBeCloseTo((300 - camera.x) / camera.scale);
    const fitted = fitCamera({ x: 2000, y: -1000, width: 600, height: 400 }, 1000, 800);
    expect(2000 * fitted.scale + fitted.x).toBeGreaterThan(0);
    expect(-1000 * fitted.scale + fitted.y).toBeGreaterThan(0);
    expect(resizeRect({ x: 0, y: 0, width: 400, height: 300 }, -1000, -1000)).toMatchObject({ width: 280, height: 240 });
  });
  it("places palette drops in world coordinates and finds free space for repeated additions", () => {
    const drop = insertionRect({ x: -120, y: 30, scale: 0.8 }, 300, 200);
    expect(drop).toMatchObject({ x: 525, y: 212.5 });
    const next = freeInsertionRect(drop, [drop]);
    expect(next.x).toBe(drop.x + drop.width + 24);
    const third = freeInsertionRect(drop, [drop, next]);
    expect(third.x).toBe(next.x + next.width + 24);
    expect(insertionRect({ x: -1e8, y: 1e8, scale: 0.15 }, 0, 0)).toMatchObject({ x: 10000, y: -10000 });
  });
  it("does not round positive throughput to zero or format absent metrics as zero", () => {
    expect(formatMetric(0.0032, "rate", "it")).toBe("0,0032/h");
    expect(formatMetric(null, "rate", "it")).toBe("—");
    expect(formatMetric(NaN, "rate", "it")).toBe("—");
  });
});
