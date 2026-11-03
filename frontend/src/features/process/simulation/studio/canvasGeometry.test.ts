import { describe, expect, it } from "vitest";
import { defaultLayout, layoutSchema } from "../dashboard/dashboardModel";
import { formatMetric } from "../dashboard/dashboardFormatting";
import { bounds, fitCamera, sceneRects, materializeScene, zoomCamera, normalizeCanvasWheel, resizeRect, insertionRect, freeInsertionRect } from "./canvasGeometry";

describe("canvas wheel navigation", () => {
  const viewport = { width: 1000, height: 700 };

  it("preserves fractional trackpad pixels and makes line scrolling travel the same distance", () => {
    expect(normalizeCanvasWheel({ deltaMode: 0, deltaX: 2.5, deltaY: -7.25 }, viewport)).toEqual({ dx: 2.5, dy: -7.25 });
    const lines = normalizeCanvasWheel({ deltaMode: 1, deltaX: 2, deltaY: -3 }, viewport);
    expect(lines).toEqual({ dx: 32, dy: -48 });
    expect(lines).toEqual(normalizeCanvasWheel({ deltaMode: 0, deltaX: 32, deltaY: -48 }, viewport));
  });

  it("uses each viewport dimension for page-sized movement", () => {
    expect(normalizeCanvasWheel({ deltaMode: 2, deltaX: 1, deltaY: -1 }, viewport)).toEqual({ dx: 1000, dy: -700 });
  });

  it("pans horizontally with Shift for pixel, line and page wheels", () => {
    expect(normalizeCanvasWheel({ deltaMode: 0, deltaX: 0, deltaY: 24, shiftKey: true }, viewport)).toEqual({ dx: 24, dy: 0 });
    expect(normalizeCanvasWheel({ deltaMode: 1, deltaX: 0, deltaY: 3, shiftKey: true }, viewport)).toEqual({ dx: 48, dy: 0 });
    expect(normalizeCanvasWheel({ deltaMode: 2, deltaX: 0, deltaY: 1, shiftKey: true }, viewport)).toEqual({ dx: 1000, dy: 0 });
  });

  it("preserves browser-translated Shift trackpad motion and redirects diagonal movement", () => {
    expect(normalizeCanvasWheel({ deltaMode: 0, deltaX: 36.5, deltaY: 0, shiftKey: true }, viewport)).toEqual({ dx: 36.5, dy: 0 });
    expect(normalizeCanvasWheel({ deltaMode: 0, deltaX: 12, deltaY: 24, shiftKey: true }, viewport)).toEqual({ dx: 36, dy: 0 });
  });

  it("keeps Ctrl/Cmd zoom working with Shift and anchors equivalent wheel units to the pointer", () => {
    const camera = { x: -80, y: 25, scale: 0.8 };
    const pixels = normalizeCanvasWheel({ deltaMode: 0, deltaX: 0, deltaY: -48, ctrlKey: true }, viewport);
    for (const modifier of [{ ctrlKey: true }, { metaKey: true }]) {
      const lines = normalizeCanvasWheel({ deltaMode: 1, deltaX: 0, deltaY: -3, shiftKey: true, ...modifier }, viewport);
      const zoomed = zoomCamera(camera, Math.exp(-lines.dy * 0.002), 300, 200);
      expect(zoomed).toEqual(zoomCamera(camera, Math.exp(-pixels.dy * 0.002), 300, 200));
      expect((300 - zoomed.x) / zoomed.scale).toBeCloseTo((300 - camera.x) / camera.scale);
      expect((200 - zoomed.y) / zoomed.scale).toBeCloseTo((200 - camera.y) / camera.scale);
    }
  });
});

describe("analytical scene", () => {
  it("migrates legacy layouts without mutating or dropping analytical objects", () => {
    const layout = defaultLayout(), original = structuredClone(layout);
    const rects = sceneRects(layout);
    expect(Object.keys(rects)).toHaveLength(7);
    expect(layout).toEqual(original);
    expect(bounds(Object.values(rects)).height).toBeGreaterThan(rects.__process__.height);
  });
  it("never overlaps generated positions for half, full or resized process layouts", () => {
    for (const width of [900, 920, 1284]) for (const fullWidgets of [false, true]) {
      const layout = defaultLayout();
      layout.process.canvas = { x: 120, y: -70, width, height: 480 };
      if (fullWidgets) layout.groups[0].widgets[2].width = "full";
      const rects = Object.values(sceneRects(layout));
      for (let a = 0; a < rects.length; a++) for (let b = a + 1; b < rects.length; b++) {
        const left = rects[a], right = rects[b];
        expect(left.x < right.x + right.width && left.x + left.width > right.x && left.y < right.y + right.height && left.y + left.height > right.y).toBe(false);
      }
    }
  });
  it("keeps other objects fixed when a migrated process is moved or resized", () => {
    const original = sceneRects(defaultLayout());
    const layout = materializeScene(defaultLayout());
    layout.process.canvas = { ...layout.process.canvas!, x: 1000, y: -300, width: 920 };
    const moved = sceneRects(layout);
    for (const widget of layout.groups.flatMap(group => group.widgets)) expect(moved[widget.id]).toEqual(original[widget.id]);
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
  it("fits above the floating navigation bars so they never cover the scene", () => {
    const rect = { x: 0, y: 0, width: 900, height: 700 };
    const fitted = fitCamera(rect, 1000, 800, 72);
    const bottom = (rect.y + rect.height) * fitted.scale + fitted.y;
    expect(bottom).toBeLessThanOrEqual(800 - 72);
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
