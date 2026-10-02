import { z } from "zod";
import { evaluateExpression } from "./dashboardExpressions";

import type { ReplayEngine, ReplayFrame } from "../replay/replayEngine";

export const KINDS = ["line", "area", "bar", "column", "pie", "donut", "gauge", "radial", "kpi", "table", "text"] as const;
export const METRICS = ["active", "queued", "completed", "throughput", "cost", "cycle", "activityActive", "activityQueued", "activityDone", "resourceBusy"] as const;
export type WidgetKind = typeof KINDS[number];
export type Metric = typeof METRICS[number];
export type Unit = "count" | "rate" | "currency" | "duration" | "percent";

export const canvasRectSchema = z.object({
  x: z.number().finite().min(-10000).max(10000), y: z.number().finite().min(-10000).max(10000),
  width: z.number().finite().min(280).max(2400), height: z.number().finite().min(240).max(1600),
});
export type CanvasRect = z.infer<typeof canvasRectSchema>;

export const widgetSchema = z.object({
  id: z.string().min(1).max(80),
  title: z.string().max(120),
  kind: z.enum(KINDS),
  metric: z.enum(METRICS),
  width: z.enum(["half", "full"]),
  text: z.string().max(4000),
  metricExpression: z.string().max(512).default(""),
  target: z.number().positive().finite(),
  followFilter: z.boolean(),
  activityId: z.string().max(200).default(""),
  showLabels: z.boolean(),
  color: z.enum(["blue", "amber", "teal", "violet"]),
  canvas: canvasRectSchema.optional(),
});
export type DashboardWidget = z.infer<typeof widgetSchema>;
export const layoutSchema = z.object({
  version: z.literal(1),
  process: z.object({
    canvas: canvasRectSchema.optional(),
    groupId: z.string().max(80), beforeId: z.string().max(80).nullable(),
    width: z.enum(["half", "full"]), height: z.number().int().min(340).max(720),
  }).default({ groupId: "", beforeId: "__first__", width: "half", height: 440 }),
  groups: z.array(z.object({
    id: z.string().min(1).max(80),
    title: z.string().max(120),
    widgets: z.array(widgetSchema).max(24),
  })).min(1).max(12),
}).superRefine((layout, ctx) => {
  const ids = layout.groups.flatMap((group) => [group.id, ...group.widgets.map((widget) => widget.id)]);
  if (new Set(ids).size !== ids.length) ctx.addIssue({ code: "custom", message: "Duplicate identifiers" });
});
export type DashboardLayout = z.infer<typeof layoutSchema>;

export function createWidget(kind: WidgetKind, id: string = crypto.randomUUID()): DashboardWidget {
  return { id, title: "", kind, metric: ["bar", "column", "pie", "donut", "radial"].includes(kind) ? "activityQueued" : "completed",
    width: "half", activityId: "", metricExpression: "", text: "**${metric}**", target: 100, followFilter: true, showLabels: true, color: "blue" };
}

export function defaultLayout(): DashboardLayout {
  const spec: [WidgetKind, Metric, DashboardWidget["color"]][] = [
    ["area", "active", "blue"], ["line", "throughput", "blue"],
    ["bar", "activityQueued", "amber"], ["column", "resourceBusy", "blue"],
    ["area", "cost", "blue"], ["line", "cycle", "blue"],
  ];
  return { version: 1, process: { groupId: "operations", beforeId: "default-0", width: "half", height: 440 }, groups: [{ id: "operations", title: "", widgets: spec.map(([kind, metric, color], index) => ({
    ...createWidget(kind, `default-${index}`), metric, color,
  })) }] };
}

/** Reorder within a section or move across sections without dropping widgets. */
export function moveWidget(layout: DashboardLayout, id: string, groupId: string, beforeId?: string): DashboardLayout {
  const widget = layout.groups.flatMap((group) => group.widgets).find((item) => item.id === id);
  if (!widget || !layout.groups.some((group) => group.id === groupId) || beforeId === id) return layout;
  const groups = layout.groups.map((group) => ({ ...group, widgets: group.widgets.filter((item) => item.id !== id) }));
  const group = groups.find((item) => item.id === groupId)!;
  const index = beforeId ? group.widgets.findIndex((item) => item.id === beforeId) : -1;
  group.widgets.splice(index < 0 ? group.widgets.length : index, 0, widget);
  if (group.widgets.length > 24) return layout;
  return { ...layout, groups };
}

const SERIES: Partial<Record<Metric, string>> = {
  active: "wip", queued: "queued", completed: "done", throughput: "throughputPerHour", cost: "costAccrued", cycle: "avgCycleSec",
};
export const UNITS: Record<Metric, Unit> = {
  active: "count", queued: "count", completed: "count", throughput: "rate", cost: "currency", cycle: "duration",
  activityActive: "count", activityQueued: "count", activityDone: "count", resourceBusy: "percent",
};
export type DashboardPoint = { label: string; value: number; t?: number };

export function widgetData(engine: ReplayEngine, frame: ReplayFrame, metric: Metric, activityId = "all") {
  const field = SERIES[metric];
  const unit = UNITS[metric];
  const numeric = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
  if (field) {
    const series = engine.payload.series.global[field];
    const value = series?.[frame.bucket];
    const observed = metric !== "cycle" || frame.global.completedCases > 0;
    const points: DashboardPoint[] = engine.payload.series.t.slice(0, frame.bucket + 1).flatMap((t, index) => {
      const v = series?.[index];
      const done = engine.payload.series.global.done?.[index] ?? 0;
      return numeric(v) && (metric !== "cycle" || done > 0) ? [{ label: String(t), t, value: v }] : [];
    });
    return { unit, categorical: false, filtered: false, value: numeric(value) && observed ? value : null, points };
  }
  const resource = metric === "resourceBusy";
  const all: DashboardPoint[] = resource
    ? Object.entries(frame.resources).map(([label, state]) => ({ label, value: state.busy * 100 }))
    : Object.entries(frame.elements).filter(([id]) => activityId === "all" || id === activityId).map(([id, state]) => ({
      label: engine.payload.elements[id]?.name ?? id,
      value: metric === "activityQueued" ? state.queued : metric === "activityDone" ? state.done : state.active,
    }));
  const points = all.filter((point) => numeric(point.value));
  const total = points.reduce((sum, point) => sum + point.value, 0);
  return { unit, categorical: true, filtered: !resource && activityId !== "all", value: points.length ? (resource ? total / points.length : total) : null, points };
}

/** Numeric formulas keep the source metric's unit and use only observed data. */
export function resolveWidgetData(engine: ReplayEngine, frame: ReplayFrame, widget: DashboardWidget, activityId: string, lang: "it" | "en") {
  const data = widgetData(engine, frame, widget.metric, widget.activityId || (widget.followFilter ? activityId : "all"));
  if (!widget.metricExpression.trim()) return { ...data, expressionValid: true };
  const calculate = (metric: number, bucket: number) => {
    const total = (engine.payload.series.global.wip?.[bucket] ?? 0) + (engine.payload.series.global.done?.[bucket] ?? 0);
    const result = evaluateExpression(widget.metricExpression, { metric, total, currentTime: engine.startMs + engine.payload.series.t[bucket] * 1000 }, lang);
    if (typeof result !== "number" || !Number.isFinite(result) || result < 0) throw new Error("numeric metric");
    return result;
  };
  try {
    const value = calculate(data.value ?? 0, frame.bucket);
    const points = data.points.flatMap((point) => {
      // A zero denominator at an earlier time is a missing observation.
      try { return [{ ...point, value: calculate(point.value, point.t === undefined ? frame.bucket : engine.payload.series.t.indexOf(point.t)) }]; }
      catch { return []; }
    });
    return { ...data, value: data.value === null ? null : value, points, expressionValid: true };
  } catch { return { ...data, value: null, points: [], expressionValid: false }; }
}
