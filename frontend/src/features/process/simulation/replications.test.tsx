import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ReplicationTable } from "./ReplicationSummary";
import { compareGroups, deltaInterval, groupMembers, interval, replicationIntervals } from "./replications";
import { DEFAULT_SCENARIO, scenarioToInput } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

const member = (index: number, cycle: number, status: SimulationRun["status"] = "completed") => ({
  id: index, status, request: { replication_group: "g1", replication_index: index },
  summary: status === "completed" ? { cycle: { avg: cycle }, waiting: { avg: cycle / 2 }, cost: { perCase: 50 }, throughputPerHour: 2 } : null,
}) as unknown as SimulationRun;

describe("replications (SIM-04)", () => {
  it("computes a 95% interval with the Student t", () => {
    const value = interval([10, 12, 14]);
    expect(value?.mean).toBe(12);
    // s = 2, t(2) = 4.303: 4.303 * 2 / sqrt(3)
    expect(value?.half).toBeCloseTo(4.969, 2);
    expect(interval([5])).toBeNull();
  });

  it("finds the members of the group in order and ignores the others", () => {
    const others = { id: 9, status: "completed", request: {} } as unknown as SimulationRun;
    const runs = [member(2, 100), others, member(1, 120)];
    expect(groupMembers(runs[0], runs).map((r) => r.id)).toEqual([1, 2]);
    expect(groupMembers(others, runs)).toEqual([]);
  });

  it("uses only completed members", () => {
    expect(replicationIntervals([member(1, 3600), member(2, 3600), member(3, 0, "pending")]).cycle).toEqual({ mean: 3600, half: 0, n: 2 });
  });

  it("shows progress, then each KPI with its interval", () => {
    const runs = [member(1, 3600), member(2, 4200), member(3, 0, "pending")];
    render(<ReplicationTable run={runs[0]} runs={runs} />);
    const section = screen.getByRole("region", { name: "Ripetizioni dello scenario" });
    expect(section).toHaveTextContent("Ripetizioni completate: 2 di 3.");
    expect(section).toHaveTextContent("Durata media del caso");
    expect(section).toHaveTextContent("±");
  });

  it("sends replications only above one", () => {
    expect(scenarioToInput({ ...structuredClone(DEFAULT_SCENARIO), replications: 5 }, null).replications).toBe(5);
    expect(scenarioToInput({ ...structuredClone(DEFAULT_SCENARIO), replications: 1 }, null)).not.toHaveProperty("replications");
  });
});

describe("delta between two repeated scenarios (SIM-04)", () => {
  const run = (id: number, group: string, index: number, seed: number, cycle: number) => ({
    id, status: "completed", request: { replication_group: group, replication_index: index, seed },
    summary: { cycle: { avg: cycle }, waiting: { avg: cycle / 2 }, cost: { perCase: 50 }, throughputPerHour: 2 },
  }) as unknown as SimulationRun;

  it("says better only when the interval leaves zero out", () => {
    expect(deltaInterval([100, 102, 98], [80, 82, 78], "lower", false)?.verdict).toBe("better");
    expect(deltaInterval([100, 102, 98], [120, 122, 118], "lower", false)?.verdict).toBe("worse");
    expect(deltaInterval([100, 140, 60], [95, 135, 55], "lower", false)?.verdict).toBe("unclear");
    expect(deltaInterval([5], [4, 3], "lower", false)).toBeNull();
  });

  it("uses the Welch interval for independent groups", () => {
    // var 4 e 4, n 3 e 3: se = sqrt(8/3), df = 4, t = 2.776
    const value = deltaInterval([10, 12, 14], [20, 22, 24], "lower", false);
    expect(value?.delta).toBe(10);
    expect(value?.half).toBeCloseTo(2.776 * Math.sqrt(8 / 3), 3);
  });

  it("pairs replications run with the same seeds, and the interval tightens", () => {
    const a = [run(1, "a", 1, 7, 100), run(2, "a", 2, 8, 140), run(3, "a", 3, 9, 60)];
    const b = [run(4, "b", 1, 7, 90), run(5, "b", 2, 8, 131), run(6, "b", 3, 9, 49)];
    const paired = compareGroups(a[0], b[0], [...a, ...b]);
    expect(paired?.paired).toBe(true);
    expect(paired?.kpis.cycle?.verdict).toBe("better");

    const shifted = b.map((r) => ({ ...r, request: { ...r.request, seed: Number(r.request.seed) + 100 } }));
    const independent = compareGroups(a[0], shifted[0], [...a, ...shifted]);
    expect(independent?.paired).toBe(false);
    expect(independent?.kpis.cycle?.verdict).toBe("unclear");
  });

  it("needs two completed replications on both sides, in two different groups", () => {
    const a = [run(1, "a", 1, 7, 100), run(2, "a", 2, 8, 120)];
    const single = { ...run(3, "", 0, 1, 90), request: {} } as SimulationRun;
    expect(compareGroups(a[0], single, [...a, single])).toBeNull();
    expect(compareGroups(a[0], a[1], a)).toBeNull();
  });
});

describe("delta interval edge cases", () => {
  it("falls back to the pooled degrees of freedom when the Welch value does not exist", () => {
    const value = deltaInterval([1e-200, 2e-200, 3e-200], [5, 5, 5], "lower", false);
    expect(Number.isFinite(value?.half)).toBe(true);
    expect(value?.verdict).toBe("worse");
  });
});
