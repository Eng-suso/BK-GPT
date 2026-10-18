import { describe, expect, it } from "vitest";

import { i18n } from "@/lib/i18n";

import { dominantBottleneck, interpret, interpretationLines } from "./interpretation";
import type { ScenarioDelta, ScenarioRuns } from "./scenarioWorkspace";
import type { SimulationRun } from "./simulationTypes";

const t = i18n.getFixedT("it", "process") as unknown as (key: string, options?: Record<string, unknown>) => string;
const format = { duration: (s: number) => `${Math.round(s / 60)} min`, currency: (v: number) => `${v.toFixed(2)} €` };

const run = (bottleneck: { el: string; name: string } | null, waits: Record<string, number>, cycle = 3600) => ({
  status: "completed",
  summary: {
    cycle: { avg: cycle }, waiting: { avg: 0 }, cost: { perCase: 50 }, throughputPerHour: 1,
    bottleneck,
    byActivity: Object.entries(waits).map(([el, avg]) => ({ el, name: el, wait: { avg } })),
  },
}) as unknown as SimulationRun;
const results = (...runs: SimulationRun[]): ScenarioRuns => ({ latest: runs[0], members: runs, completed: runs, status: "current", bpmnChanged: false });
const single = (delta: number): ScenarioDelta => ({ kind: "single", delta, direction: delta < 0 ? "better" : "worse" });
const interval = (delta: number, verdict: "better" | "worse" | "unclear"): ScenarioDelta => ({
  kind: "interval", paired: true, value: { a: 0, b: 0, delta, half: 1, verdict, probBetter: 0.5, comparisons: 1 },
});

const approve = { el: "A", name: "Approva" };
const pay = { el: "P", name: "Paga" };

describe("interpretation (SIM-24)", () => {
  it("says where the constraint moves, with the wait in front of the old one", () => {
    const value = interpret(results(run(approve, { A: 2400 })), results(run(pay, { A: 300 })), { kpis: { cycle: single(-1800), costPerCase: single(3) }, mismatch: false });
    expect(value.constraint).toMatchObject({ kind: "moved", from: approve, to: pay, waitBefore: 2400, waitAfter: 300 });
    expect(interpretationLines(value, t, format)).toEqual([
      "Il vincolo si sposta da «Approva» a «Paga». Attesa media lì: 40 min → 5 min.",
      "Più veloce di 30 min per caso, al costo di 3.00 € in più: 6.00 € per ogni ora risparmiata.",
    ]);
  });

  it("does not tell an uncertain difference as a gain", () => {
    const value = interpret(results(run(approve, {})), results(run(approve, {})), { kpis: { cycle: interval(-60, "unclear"), costPerCase: interval(1, "unclear") }, mismatch: false });
    expect(value.tradeOff).toEqual({ kind: "unclear" });
    expect(interpretationLines(value, t, format)[0]).toBe("Il vincolo resta «Approva».");
  });

  it("names a change on one side only, and the cheaper-but-slower trade", () => {
    const onlyFaster = interpret(results(run(null, {})), results(run(null, {})), { kpis: { cycle: interval(-600, "better"), costPerCase: interval(0.5, "unclear") }, mismatch: false });
    expect(interpretationLines(onlyFaster, t, format)).toEqual(["Più veloce di 10 min per caso, a costo invariato."]);
    const cheaper = interpret(results(run(approve, {})), results(run(null, {})), { kpis: { cycle: single(7200), costPerCase: single(-10) }, mismatch: false });
    expect(cheaper.constraint.kind).toBe("relieved");
    expect(cheaper.tradeOff).toMatchObject({ kind: "cheaper", perHour: 5 });
  });

  it("stays silent on the trade-off across different models", () => {
    const value = interpret(results(run(null, {})), results(run(null, {})), { kpis: { cycle: null, costPerCase: null }, mismatch: true });
    expect(value.tradeOff).toEqual({ kind: "unknown" });
  });

  it("takes the most frequent bottleneck across replications", () => {
    expect(dominantBottleneck([run(approve, {}), run(pay, {}), run(pay, {})])).toEqual(pay);
    expect(dominantBottleneck([run(null, {})])).toBeNull();
  });
});
