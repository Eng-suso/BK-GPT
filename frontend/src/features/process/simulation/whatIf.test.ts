import { describe, expect, it } from "vitest";

import { diffScenario } from "./scenarioPatch";
import type { ScenarioDraft } from "./simulationScenario";
import { applyWhatIf, whatIfContext } from "./whatIf";

const draft = {
  scenarioName: "Base",
  arrivalIntervalMinutes: 30,
  arrival: { distribution: "expon", bands: [{ fromDay: "mon", toDay: "fri", begin: "09:00", end: "12:00", meanMinutes: 10 }] },
  resources: [
    { id: "r1", name: "Approvatore", costPerHour: 40, amount: 2, parametersConfirmed: true },
    { id: "r2", name: "", costPerHour: 30, amount: 1 },
  ],
  tasks: {
    T: { meanMinutes: 20, distribution: "norm", stdMinutes: 4, resourceId: "r1",
      otherAssignments: [{ resourceId: "r2", meanMinutes: 30, distribution: "fixed" }] },
    U: { meanMinutes: 15, distribution: "norm", resourceId: "r2", skip: { percent: 10, rule: { groups: [] } } },
  },
  gateways: {},
} as unknown as ScenarioDraft;

describe("applyWhatIf (SIM-23)", () => {
  it("shows the model the activities and roles with their names, or their ids", () => {
    expect(whatIfContext(draft, { T: "Verifica" })).toEqual({
      activities: [{ id: "T", name: "Verifica" }, { id: "U", name: "U" }],
      resources: [{ id: "r1", name: "Approvatore", units: 2 }, { id: "r2", name: "r2", units: 1 }],
    });
  });

  it("a large process sends at most the activities and roles the backend accepts", () => {
    const tasks = Object.fromEntries(Array.from({ length: 250 }, (_, i) => [`T${i}`, { meanMinutes: 5 }]));
    const resources = Array.from({ length: 120 }, (_, i) => ({ id: `r${i}`, name: "x".repeat(300), amount: 1, costPerHour: 0 }));
    const context = whatIfContext({ ...draft, tasks, resources } as unknown as ScenarioDraft, {});
    expect(context.activities).toHaveLength(200);
    expect(context.resources).toHaveLength(100);
    expect(context.resources[0]?.name).toHaveLength(200);
  });

  it("sets the units of a role and asks to confirm its parameters again", () => {
    const { draft: next, skipped } = applyWhatIf(draft, [{ kind: "resource_units", resource_id: "r1", units: 3 }]);
    expect(next.resources[0]).toMatchObject({ amount: 3, parametersConfirmed: false });
    expect(next.resources[1]).toBe(draft.resources[1]);
    expect(skipped).toEqual([]);
  });

  it("scales every duration of the activity, other roles included", () => {
    const { draft: next } = applyWhatIf(draft, [{ kind: "activity_duration", element_id: "T", factor: 0.5, mean_minutes: null }]);
    expect(next.tasks.T).toMatchObject({ meanMinutes: 10, stdMinutes: 2, otherAssignments: [{ meanMinutes: 15 }] });
  });

  it("a new mean keeps the proportions of the other durations", () => {
    const { draft: next } = applyWhatIf(draft, [{ kind: "activity_duration", element_id: "T", factor: null, mean_minutes: 40 }]);
    expect(next.tasks.T).toMatchObject({ meanMinutes: 40, stdMinutes: 8, otherAssignments: [{ meanMinutes: 60 }] });
  });

  it("skipping a step applies to every case: the old rule goes", () => {
    const { draft: next } = applyWhatIf(draft, [{ kind: "skip_activity", element_id: "U", percent: 100 }]);
    expect(next.tasks.U?.skip).toEqual({ percent: 100 });
  });

  it("more demand means shorter gaps between arrivals, in the bands too", () => {
    const { draft: next } = applyWhatIf(draft, [{ kind: "demand", factor: 1.25 }]);
    expect(next.arrivalIntervalMinutes).toBe(24);
    expect(next.arrival?.bands?.[0]?.meanMinutes).toBe(8);
  });

  it("changes the hourly cost of a role", () => {
    const { draft: next } = applyWhatIf(draft, [{ kind: "resource_cost", resource_id: "r2", cost_per_hour: 55 }]);
    expect(next.resources[1]?.costPerHour).toBe(55);
  });

  it("a change on something no longer in the draft has no effect and is reported", () => {
    const gone = { kind: "resource_units" as const, resource_id: "r9", units: 2 };
    const { draft: next, skipped } = applyWhatIf(draft, [gone]);
    expect(next).toBe(draft);
    expect(skipped).toEqual([gone]);
  });

  it("the preview is a patch with only what the sentence asked", () => {
    const { draft: next } = applyWhatIf(draft, [
      { kind: "resource_units", resource_id: "r1", units: 3 },
      { kind: "skip_activity", element_id: "U", percent: 100 },
    ]);
    expect(diffScenario(draft, next)).toEqual([
      { op: "set", path: ["resources", { id: "r1" }, "amount"], value: 3 },
      { op: "set", path: ["resources", { id: "r1" }, "parametersConfirmed"], value: false },
      { op: "set", path: ["tasks", "U", "skip", "percent"], value: 100 },
      { op: "remove", path: ["tasks", "U", "skip", "rule"] },
    ]);
  });
});
