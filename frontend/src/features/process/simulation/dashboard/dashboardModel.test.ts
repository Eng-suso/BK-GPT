import { describe, expect, it } from "vitest";
import { defaultLayout, layoutSchema, moveWidget, widgetData } from "./dashboardModel";
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
