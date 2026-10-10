import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ReplicationTable } from "./ReplicationSummary";
import { groupMembers, interval, replicationIntervals } from "./replications";
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
