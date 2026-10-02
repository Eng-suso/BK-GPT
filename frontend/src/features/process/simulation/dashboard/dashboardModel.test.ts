import { describe, expect, it } from "vitest";
import { createWidget, resolveWidgetData, defaultLayout, layoutSchema, moveWidget, widgetData } from "./dashboardModel";
import { evaluateExpression, interpolateText } from "./dashboardExpressions";
import { ReplayEngine } from "../replay/replayEngine";

describe("dashboard expressions", () => {
  const vars = { metric: 3, total: 8 };
  it("supports nested functions, precedence and localized percentages", () => {
    expect(evaluateExpression("formatPercentage(round(metric / total, 2))", vars, "en")).toBe("38%");
    expect(evaluateExpression("(total - metric) * 2 + 1", vars, "it")).toBe(11);
  });
  it("keeps the original draft when a formula is invalid or divides by zero", () => {
    expect(interpolateText("**${metric / total}**", { metric: 1, total: 0 }, "it")).toEqual({ text: "**${metric / total}**", valid: false });
    expect(interpolateText("${metric", vars, "it").valid).toBe(false);
  });
  it("rejects object access, constructors and unbounded nesting", () => {
    for (const source of ["globalThis.alert(1)", "constructor(1)", "metric.toString()", "(".repeat(20) + "1" + ")".repeat(20)]) {
      expect(() => evaluateExpression(source, vars, "en")).toThrow();
    }
  });
});

describe("dashboard configuration", () => {
  it("rejects corrupted persisted layouts and duplicate widget identifiers", () => {
    const layout = defaultLayout();
    expect(layoutSchema.safeParse({ ...layout, version: 99 }).success).toBe(false);
    layout.groups[0].widgets.push(layout.groups[0].widgets[0]);
    expect(layoutSchema.safeParse(layout).success).toBe(false);
  });
  it("moves widgets between sections without mutating the saved configuration", () => {
    const layout = defaultLayout();
    layout.groups.push({ id: "second", title: "Second", widgets: [] });
    const moved = moveWidget(layout, "default-0", "second");
    expect(moved.groups[1].widgets[0].id).toBe("default-0");
    expect(moved.groups.flatMap((group) => group.widgets)).toHaveLength(6);
    expect(layout.groups[0].widgets[0].id).toBe("default-0");
  });
});

it("never exposes future data or a cycle average before a case completes", () => {
  const engine = new ReplayEngine({
    schemaVersion: 1, meta: { start: "2026-01-01T00:00:00Z", durationSec: 200, totalCases: 2, sampledCases: 0, bucketSec: 100 },
    elements: {}, cases: [], flows: {}, series: { t: [0, 100, 200], byElement: {}, byResource: {},
      global: { done: [0, 1, 2], avgCycleSec: [0, 50, 75], costAccrued: [0, 10, 999] } },
  });
  expect(widgetData(engine, engine.getFrame(), "cycle").value).toBeNull();
  engine.seek(100);
  expect(widgetData(engine, engine.getFrame(), "cost").points.map((point) => point.value)).toEqual([0, 10]);
  expect(widgetData(engine, engine.getFrame(), "cycle").value).toBe(50);
  expect(widgetData(engine, engine.getFrame(), "throughput").value).toBeNull();
});

it("computes numeric KPI formulas at each observed time and preserves existing layouts", () => {
  const engine = new ReplayEngine({
    schemaVersion: 1, meta: { start: "2026-01-01T00:00:00Z", durationSec: 200, totalCases: 10, sampledCases: 0, bucketSec: 100 },
    elements: {}, cases: [], flows: {}, series: { t: [0, 100, 200], byElement: {}, byResource: {},
      global: { wip: [0, 1, 0], done: [0, 1, 10], costAccrued: [0, 20, 999] } },
  });
  engine.seek(100);
  const widget = { ...createWidget("kpi"), metric: "cost" as const, metricExpression: "round(metric / total, 2)" };
  const data = resolveWidgetData(engine, engine.getFrame(), widget, "all", "it");
  expect(data.value).toBe(10);
  expect(data.points.map((point) => point.value)).toEqual([10]);
  expect(resolveWidgetData(engine, engine.getFrame(), { ...widget, metricExpression: "metric / 0" }, "all", "en").expressionValid).toBe(false);
  const layout = defaultLayout();
  const legacy = { ...layout, groups: layout.groups.map((group) => ({ ...group, widgets: group.widgets.map((widget) => { const rest: Record<string, unknown> = { ...widget }; delete rest.metricExpression; return rest; }) })) };
  expect(layoutSchema.parse(legacy).groups[0].widgets[0].metricExpression).toBe("");
});


it("migrates a saved dashboard without losing widgets or activity settings", () => {
  const { process: ignored, ...legacy } = defaultLayout();
  void ignored;
  const parsed = layoutSchema.parse({ ...legacy, groups: legacy.groups.map((group) => ({ ...group, widgets: group.widgets.map((widget) => { const { activityId: unused, ...old } = widget; void unused; return old; }) })) });
  expect(parsed.groups[0].widgets.map((widget) => widget.id)).toEqual(legacy.groups[0].widgets.map((widget) => widget.id));
  expect(parsed.process.beforeId).toBe("__first__");
  expect(parsed.groups[0].widgets[0].activityId).toBe("");
});

it("keeps an explicitly bound activity independent from the current selection", () => {
  const engine = new ReplayEngine({
    schemaVersion: 1, meta: { start: "2026-01-01T00:00:00Z", durationSec: 100, totalCases: 4, sampledCases: 0, bucketSec: 100 },
    elements: { A: { name: "Review" }, B: { name: "Approve" } }, cases: [], flows: {},
    series: { t: [0, 100], global: {}, byResource: {}, byElement: { A: { queued: [2, 0], active: [0, 0], done: [0, 0] }, B: { queued: [4, 1], active: [0, 0], done: [0, 0] } } },
  });
  const widget = { ...createWidget("kpi"), metric: "activityQueued" as const, activityId: "A", followFilter: false };
  expect(resolveWidgetData(engine, engine.getFrame(), widget, "B", "en").value).toBe(2);
  engine.seek(100);
  expect(resolveWidgetData(engine, engine.getFrame(), widget, "B", "en").value).toBe(0);
});
