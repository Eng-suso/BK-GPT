import type { CanvasRect, DashboardLayout } from "../dashboard/dashboardModel";

export type Camera = { x: number; y: number; scale: number };
export const PROCESS_ID = "__process__";

/** Deterministic migration: preserve every legacy widget and never write until Save. */
export function sceneRects(layout: DashboardLayout): Record<string, CanvasRect> {
  const process = layout.process.canvas ?? { x: 0, y: 0, width: layout.process.width === "full" ? 1284 : 900, height: Math.max(620, layout.process.height) };
  const result: Record<string, CanvasRect> = { [PROCESS_ID]: process };
  let index = 0;
  for (const group of layout.groups) for (const widget of group.widgets) {
    const top = index < 2 && process.width === 900;
    const slot = top ? index : index - (process.width === 900 ? 2 : 0);
    result[widget.id] = widget.canvas ?? {
      x: top ? 924 : (slot % 3) * 440,
      y: top ? slot * 314 : process.height + 24 + Math.floor(slot / 3) * 314,
      width: widget.width === "full" ? 1284 : top ? 360 : 416, height: 290,
    };
    index++;
  }
  return result;
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
