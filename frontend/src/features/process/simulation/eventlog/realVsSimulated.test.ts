import { describe, expect, it } from "vitest";

import type { SimulationSummary } from "../simulationTypes";
import type { EventLogSummary } from "./eventLogTypes";
import { compareRealToSimulated, fidelityOf, relativeGap, worstFidelity } from "./realVsSimulated";

const activity = (el: string | null, name: string, wait: number, processing: number, count = 10) => ({
  el,
  name,
  count,
  wait: { avg: wait, p95: wait },
  processing: { avg: processing, p95: processing },
});

function real(overrides: Partial<EventLogSummary> = {}): EventLogSummary {
  return {
    casesCompleted: 100,
    cycle: { avg: 3600, p50: 3000, p90: 6000 },
    waiting: { avg: 1200 },
    processing: { avg: 2400 },
    throughputPerHour: 2,
    cost: null,
    timing: "start_and_end",
    byActivity: [activity("Task_A", "Approva", 600, 1200), activity("Task_B", "Paga", 600, 1200), activity(null, "Archivia", 0, 60), activity("Task_D", "Sollecita", 0, 60)],
    ...overrides,
  } as EventLogSummary;
}

function simulated(overrides: Partial<SimulationSummary> = {}): SimulationSummary {
  return {
    casesCompleted: 500,
    cycle: { avg: 3960, p50: 3300, p90: 8400, p95: 9000 },
    waiting: { avg: 1500 },
    processing: { avg: 2460 },
    cost: { total: 5000, perCase: 10 },
    throughputPerHour: 2.1,
    byActivity: [activity("Task_A", "Approva", 700, 1260), activity("Task_B", "Paga", 800, 2400), activity("Task_C", "Notifica", 0, 30)],
    ...overrides,
  } as unknown as SimulationSummary;
}

describe("fidelity", () => {
  it("reads the relative gap against the real log", () => {
    expect(relativeGap(100, 110)).toBeCloseTo(0.1);
    expect(relativeGap(0, 0)).toBe(0);
    expect(relativeGap(0, 5)).toBeNull();
    expect(relativeGap(null, 5)).toBeNull();
  });

  it("buckets gaps at 10% and 25%", () => {
    expect(fidelityOf(0.1)).toBe("close");
    expect(fidelityOf(-0.2)).toBe("calibrate");
    expect(fidelityOf(0.4)).toBe("far");
    expect(fidelityOf(null)).toBeNull();
    expect(fidelityOf(relativeGap(2, 2.2))).toBe("close");
    expect(worstFidelity(["close", null, "calibrate"])).toBe("calibrate");
  });
});

describe("compareRealToSimulated", () => {
  it("compares process KPIs and judges on the worst of cycle avg and P90", () => {
    const result = compareRealToSimulated(real(), simulated());
    const cycle = result.process.find((row) => row.key === "cycleAvg");
    expect(cycle?.gap).toBeCloseTo(0.1);
    expect(cycle?.fidelity).toBe("close");
    expect(result.process.find((row) => row.key === "cycleP90")?.fidelity).toBe("far");
    expect(result.fidelity).toBe("far");
  });

  it("keeps cost as not comparable when the log has no cost column", () => {
    const cost = compareRealToSimulated(real(), simulated()).process.find((row) => row.key === "costPerCase");
    expect(cost).toMatchObject({ real: null, simulated: 10, gap: null, notComparable: "noCost" });
  });

  it("does not compare waiting and processing when the log has only completions", () => {
    const result = compareRealToSimulated(real({ timing: "complete_only" }), simulated());
    expect(result.process.find((row) => row.key === "waitingAvg")?.notComparable).toBe("noStart");
    expect(result.process.find((row) => row.key === "processingAvg")?.notComparable).toBe("noStart");
    expect(result.activities.every((row) => row.processingGap === null && row.realWait === null && row.realProcessing === null)).toBe(true);
  });

  it("joins activities on the BPMN element, largest gap first", () => {
    const result = compareRealToSimulated(real(), simulated());
    expect(result.activities.map((row) => row.el)).toEqual(["Task_B", "Task_A"]);
    expect(result.activities[0]).toMatchObject({ processingGap: 1, fidelity: "far", realWait: 600, simulatedWait: 800 });
    expect(result.unmatchedReal).toEqual(["Archivia"]);
    expect(result.notSimulated).toEqual(["Sollecita"]);
    expect(result.unobservedSimulated).toEqual(["Notifica"]);
  });

  it("merges log activities mapped to the same element, weighted by executions", () => {
    const merged = real({
      byActivity: [activity("Task_A", "Approva", 600, 1200, 30), activity("Task_A", "Approva (2° livello)", 1200, 2400, 10)],
    } as Partial<EventLogSummary>);
    const [row] = compareRealToSimulated(merged, simulated()).activities;
    expect(compareRealToSimulated(merged, simulated()).activities).toHaveLength(1);
    expect(row).toMatchObject({ el: "Task_A", name: "Approva", logNames: ["Approva", "Approva (2° livello)"], realCount: 40, realWait: 750, realProcessing: 1500 });
  });
});
