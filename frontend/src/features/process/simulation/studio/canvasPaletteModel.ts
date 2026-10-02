import { KINDS, type Metric, type WidgetKind } from "../dashboard/dashboardModel";

export const PALETTE_DRAG_TYPE = "application/delir-canvas-element";
export type PaletteItem = { kind: WidgetKind; metric?: Metric; note?: boolean };
export const paletteMetrics = ["active", "queued", "completed", "throughput", "cycle", "cost"] as const;
export const paletteAnalyses: PaletteItem[] = [{ kind: "bar", metric: "activityQueued" }, { kind: "column", metric: "resourceBusy" }, { kind: "line", metric: "throughput" }, { kind: "area", metric: "active" }, { kind: "area", metric: "cost" }, { kind: "line", metric: "cycle" }];

// Only known catalog entries can cross the drag boundary.
export function parsePaletteItem(raw: string): PaletteItem | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const item = value as Record<string, unknown>;
    if (!KINDS.includes(item.kind as WidgetKind)) return null;
    if (item.metric !== undefined && ![...paletteMetrics, "activityQueued", "resourceBusy"].includes(item.metric as typeof paletteMetrics[number])) return null;
    if (item.note !== undefined && (item.note !== true || item.kind !== "text")) return null;
    return { kind: item.kind as WidgetKind, metric: item.metric as Metric | undefined, note: item.note as true | undefined };
  } catch { return null; }
}

