import type { CanvasRect, DashboardLayout } from "../dashboard/dashboardModel";

export type Camera = { x: number; y: number; scale: number };
export const PROCESS_ID = "__process__";

/** Deterministic migration: preserve every legacy widget and never write until Save. */
export function sceneRects(layout: DashboardLayout): Record<string, CanvasRect> {
  const process = layout.process.canvas ?? { x: 0, y: 0, width: layout.process.width === "full" ? 1284 : 900, height: Math.max(480, layout.process.height) };
  const result: Record<string, CanvasRect> = { [PROCESS_ID]: process };
  const widgets = layout.groups.flatMap(group => group.widgets);
  const sideCount = process.width === 900 && widgets.slice(0, 2).every(widget => widget.width !== "full") ? Math.min(2, widgets.length) : 0;
  const bottom = process.y + Math.max(process.height, sideCount * 314 - 24) + 24;
  let column = 0, row = 0;
  const occupied = [process, ...widgets.flatMap(widget => widget.canvas ? [widget.canvas] : [])];
  widgets.forEach((widget, index) => {
    if (widget.canvas) { result[widget.id] = widget.canvas; return; }
    const side = index < sideCount;
    if (!side && widget.width === "full" && column) { row++; column = 0; }
    const preferred = {
      x: process.x + (side ? 924 : column * 440),
      y: side ? process.y + index * 314 : bottom + row * 314,
      width: widget.width === "full" ? 1284 : side ? 360 : 416, height: 290,
    };
    const rect = freeInsertionRect(preferred, occupied);
    result[widget.id] = rect;
    occupied.push(rect);
    if (!side) {
      column += widget.width === "full" ? 3 : 1;
      if (column >= 3) { row++; column = 0; }
    }
  });
  return result;
}

/** Freeze fallback positions before editing one object, so unrelated objects stay put. */
export function materializeScene(layout: DashboardLayout): DashboardLayout {
  const rects = sceneRects(layout);
  return { ...layout, process: { ...layout.process, canvas: rects[PROCESS_ID] }, groups: layout.groups.map(group => ({ ...group, widgets: group.widgets.map(widget => ({ ...widget, canvas: rects[widget.id] })) })) };
}

export function bounds(rects: CanvasRect[]): CanvasRect {
  if (!rects.length) return { x: 0, y: 0, width: 900, height: 620 };
  const x = Math.min(...rects.map(r => r.x)), y = Math.min(...rects.map(r => r.y));
  return { x, y, width: Math.max(...rects.map(r => r.x + r.width)) - x, height: Math.max(...rects.map(r => r.y + r.height)) - y };
}

export function fitCamera(rect: CanvasRect, width: number, height: number): Camera {
  const scale = Math.max(0.15, Math.min(1, (width - 48) / rect.width, (height - 48) / rect.height));
  return { x: (width - rect.width * scale) / 2 - rect.x * scale, y: (height - rect.height * scale) / 2 - rect.y * scale, scale };
}

/** Zoom around the pointer rather than the scene origin. */
export function zoomCamera(camera: Camera, factor: number, x: number, y: number): Camera {
  const scale = Math.max(0.15, Math.min(2.5, camera.scale * factor));
  return { x: x - (x - camera.x) * scale / camera.scale, y: y - (y - camera.y) * scale / camera.scale, scale };
}

export function resizeRect(rect: CanvasRect, dx: number, dy: number): CanvasRect {
  return { ...rect, width: Math.max(280, Math.min(2400, rect.width + dx)), height: Math.max(240, Math.min(1600, rect.height + dy)) };
}

/** Palette drops use viewport pixels; persisted positions use scene units. */
export function insertionRect(camera: Camera, x: number, y: number): CanvasRect {
  return { x: Math.max(-10000, Math.min(10000, (x - camera.x) / camera.scale)), y: Math.max(-10000, Math.min(10000, (y - camera.y) / camera.scale)), width: 416, height: 290 };
}

/** Click-to-add seeks nearby free space, then the camera reveals the new object. */
export function freeInsertionRect(start: CanvasRect, occupied: CanvasRect[]): CanvasRect {
  const collides = (rect: CanvasRect) => occupied.some(other => rect.x < other.x + other.width + 24 && rect.x + rect.width + 24 > other.x && rect.y < other.y + other.height + 24 && rect.y + rect.height + 24 > other.y);
  for (let row = 0; row < 50; row++) {
    for (let column = 0; column < 4; column++) {
      const rect = { ...start, x: Math.min(10000, start.x + column * (start.width + 24)), y: Math.min(10000, start.y + row * (start.height + 24)) };
      if (!collides(rect)) return rect;
    }
  }
  return start;
}
