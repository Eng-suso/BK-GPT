import { describe, expect, it } from "vitest";

import { elementWaitDeltas, kpiDeltas } from "./compareDeltas";
import type { SimulationSummary } from "./simulationTypes";

function summary(over: Partial<Record<string, unknown>> = {}): SimulationSummary {
  return {
    casesCompleted: 100,
    cycle: { avg: 10000, p50: 9000, p90: 15000, p95: 18000 },
    waiting: { avg: 7000, p95: 14000, share: 0.7 },
    processing: { avg: 3000 },
    cost: { total: 5000, perCase: 50 },
    throughputPerHour: 4,
    byActivity: [
      { el: "A", name: "Alpha", wait: { avg: 4000, p95: 8000 } },
      { el: "B", name: "Beta", wait: { avg: 3000, p95: 6000 } },
    ],
    byResource: [{ id: "r", name: "R", pool: "R", utilizationPct: 90 }],
    bottleneck: null,
    ...over,
  } as unknown as SimulationSummary;
}

describe("kpiDeltas", () => {
  it("marks a lower cycle time in B as better", () => {
    const a = summary();
    const b = summary({ cycle: { avg: 8000, p50: 7000, p90: 12000, p95: 15000 } });
    const rows = kpiDeltas(a, b);
    const cycle = rows.find((r) => r.key === "cycleAvg")!;
    expect(cycle.delta).toBe(-2000);
    expect(cycle.deltaPct).toBeCloseTo(-0.2);
    expect(cycle.direction).toBe("better");
  });

  it("marks a higher throughput in B as better", () => {
    const rows = kpiDeltas(summary(), summary({ throughputPerHour: 6 }));
    expect(rows.find((r) => r.key === "throughput")!.direction).toBe("better");
  });

  it("marks a higher cost in B as worse", () => {
    const rows = kpiDeltas(summary(), summary({ cost: { total: 9000, perCase: 90 } }));
    expect(rows.find((r) => r.key === "costPerCase")!.direction).toBe("worse");
  });

  it("treats a sub-2% change as 'same'", () => {
    const rows = kpiDeltas(summary(), summary({ cycle: { avg: 10100, p50: 9000, p90: 15000, p95: 18000 } }));
    expect(rows.find((r) => r.key === "cycleAvg")!.direction).toBe("same");
  });

  it("uses busiest resource utilisation across the pool", () => {
    const b = summary({
      byResource: [
        { id: "r1", utilizationPct: 60 },
        { id: "r2", utilizationPct: 75 },
      ],
    });
    const row = kpiDeltas(summary(), b).find((r) => r.key === "busiestResource")!;
    expect(row.a).toBe(90);
    expect(row.b).toBe(75);
    expect(row.direction).toBe("better");
  });
});

describe("elementWaitDeltas", () => {
  it("returns per-element wait deltas sorted by magnitude", () => {
    const a = summary();
    const b = summary({
      byActivity: [
        { el: "A", name: "Alpha", wait: { avg: 1000 } }, // -3000
        { el: "B", name: "Beta", wait: { avg: 3500 } }, // +500
      ],
    });
    const deltas = elementWaitDeltas(a, b);
    expect(deltas.map((d) => d.el)).toEqual(["A", "B"]);
    expect(deltas[0]).toMatchObject({ deltaWait: -3000, direction: "better" });
    expect(deltas[1]).toMatchObject({ deltaWait: 500, direction: "worse" });
  });

  it("handles an element present in only one run", () => {
    const a = summary({ byActivity: [{ el: "A", name: "Alpha", wait: { avg: 4000 } }] });
    const b = summary({
      byActivity: [
        { el: "A", name: "Alpha", wait: { avg: 4000 } },
        { el: "C", name: "Gamma", wait: { avg: 2000 } },
      ],
    });
    const deltas = elementWaitDeltas(a, b);
    expect(deltas.find((d) => d.el === "C")).toMatchObject({ aWait: 0, bWait: 2000 });
  });
});
