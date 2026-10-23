import { describe, expect, it } from "vitest";

import { experimentDraft } from "./experiments";
import type { ScenarioDraft } from "./simulationScenario";
import type { Experiment } from "./simulationTypes";

const draft = {
  scenarioName: "Base",
  resources: [
    { id: "r1", name: "Back office", costPerHour: 40, amount: 1, parametersConfirmed: true },
    { id: "r2", name: "Sportello", costPerHour: 30, amount: 3, parametersConfirmed: true },
  ],
  tasks: {
    T: { meanMinutes: 20, distribution: "norm", stdMinutes: 4, resourceId: "r1",
      otherAssignments: [{ resourceId: "r2", meanMinutes: 30, distribution: "fixed" }],
      durationBy: { attributeId: "a", variants: { premium: { meanMinutes: 10, distribution: "norm" } }, thresholds: [{ upTo: 100, duration: { meanMinutes: 8, distribution: "fixed" } }] } },
    U: { meanMinutes: 15, distribution: "norm", resourceId: "r2" },
  },
  gateways: {},
} as unknown as ScenarioDraft;

const exp = (kind: Experiment["kind"], extra: Partial<Experiment> = {}): Experiment => ({
  kind, pool_id: "pool-ops", pool_name: "Back office", from_amount: 1, to_amount: 2, rationale: "",
  estimate: { cycle_pct: -0.3, cost_pct: 0.1 }, target_el: "T", ...extra,
});

describe("experimentDraft (SIM-22)", () => {
  it("removing a step skips it for every case and touches nothing else (SIM-22b)", () => {
    const next = experimentDraft(draft, exp("remove_step", { target_el: "U" }), "Senza U");
    expect(next.scenarioName).toBe("Senza U");
    expect(next.tasks.U?.skip).toEqual({ percent: 100 });
    expect(next.tasks.T).toBe(draft.tasks.T);
    expect(next.resources).toBe(draft.resources);
  });

  it("adds one unit to the bottleneck role", () => {
    const next = experimentDraft(draft, exp("add_resource"), "Base · +1");
    expect(next.resources.map((r) => [r.id, r.amount, r.parametersConfirmed])).toEqual([["r1", 2, false], ["r2", 3, true]]);
    expect(next.scenarioName).toBe("Base · +1");
  });

  it("moves one unit from the donor role", () => {
    const next = experimentDraft(draft, exp("reallocate", { donor_pool_name: "sportello" }), "x");
    expect(next.resources.map((r) => r.amount)).toEqual([2, 2]);
  });

  it("does nothing when the donor is unknown or is the bottleneck itself", () => {
    expect(experimentDraft(draft, exp("reallocate", { donor_pool_name: "Altro" }), "x")).toBe(draft);
    expect(experimentDraft(draft, exp("reallocate", { donor_pool_name: "Back office" }), "x")).toBe(draft);
  });

  it("automation halves every duration of the activity and nothing else", () => {
    const next = experimentDraft(draft, exp("automate", { share: 0.5 }), "x");
    const task = next.tasks.T;
    expect([task.meanMinutes, task.stdMinutes]).toEqual([10, 2]);
    expect(task.otherAssignments?.[0].meanMinutes).toBe(15);
    expect(task.durationBy?.variants.premium.meanMinutes).toBe(5);
    expect(task.durationBy?.thresholds?.[0].duration.meanMinutes).toBe(4);
    expect(next.tasks.U).toBe(draft.tasks.U);
    expect(next.resources).toBe(draft.resources);
  });
});
