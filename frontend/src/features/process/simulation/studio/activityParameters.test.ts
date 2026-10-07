import { describe, expect, it } from "vitest";

import type { ScenarioElementProvenance } from "../simulationTypes";
import { activityParameters, hasTaskConfig } from "./activityParameters";

const REQUEST = {
  default_task_duration_seconds: 900,
  resource_name: "Operatore",
  resource_amount: 1,
  default_cost_per_hour: 35,
  resources: [
    { id: "res-a", name: "Back office", amount: 3, cost_per_hour: 40 },
    { id: "res-b", name: "Legale", amount: 1, cost_per_hour: 90 },
  ],
  tasks: [
    { element_id: "Task_Review", mean_seconds: 2520, distribution: "expon", resource_id: "res-b" },
    { element_id: "Task_Approve", mean_seconds: 900, distribution: "norm", resource_id: "res-a" },
  ],
};

const DECLARED: ScenarioElementProvenance = {
  element_id: "Task_Review",
  kind: "activity",
  name: "Verifica",
  parameter: "duration",
  provenance: { origin: "declared", confidence: "high", sources: [{ kind: "interview", id: "steps:s1" }] },
  confidence: "high",
  evidence: ["Un operatore controlla gli allegati."],
  open_questions: 0,
  hint_ref: null,
};

describe("activityParameters", () => {
  it("reads the per-task duration, distribution and resource the run used", () => {
    const params = activityParameters(REQUEST, "Task_Review", DECLARED)!;
    expect(params).toMatchObject({
      meanSeconds: 2520,
      distribution: "expon",
      stdShareOfMean: null,
      resource: { name: "Legale", amount: 1, costPerHour: 90 },
      usesDefault: false,
    });
    expect(params.provenance).toMatchObject({ origin: "manual", confidence: "high" });
    expect(params.provenance.sources).toEqual([{ kind: "interview", id: "steps:s1" }]);
  });

  it("a task at the default duration is not consultant-set", () => {
    const params = activityParameters(REQUEST, "Task_Approve")!;
    expect(params.usesDefault).toBe(true);
    expect(params.stdShareOfMean).toBe(0.1);
    expect(params.provenance).toMatchObject({ origin: "default", confidence: "low" });
  });

  it("falls back like the backend when the task has no override", () => {
    const params = activityParameters({ ...REQUEST, resources: null, tasks: null }, "Task_X")!;
    expect(params).toMatchObject({
      meanSeconds: 900,
      distribution: "norm",
      resource: { name: "Operatore", amount: 1, costPerHour: 35 },
      usesDefault: true,
    });
  });

  it("an unknown resource id falls back to the first resource", () => {
    const request = { ...REQUEST, tasks: [{ element_id: "Task_Y", mean_seconds: 60, resource_id: "gone" }] };
    expect(activityParameters(request, "Task_Y")?.resource?.name).toBe("Back office");
  });

  it("returns null without a request or a selection", () => {
    expect(activityParameters(null, "Task_Review")).toBeNull();
    expect(activityParameters(REQUEST, "")).toBeNull();
  });
  it("knows which elements the run configured as tasks", () => {
    expect(hasTaskConfig(REQUEST, "Task_Review")).toBe(true);
    expect(hasTaskConfig(REQUEST, "Gateway_1")).toBe(false);
    expect(hasTaskConfig(null, "Task_Review")).toBe(false);
  });
});
