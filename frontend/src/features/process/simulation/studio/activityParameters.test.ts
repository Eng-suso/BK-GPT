import { describe, expect, it } from "vitest";

import type { ScenarioElementProvenance } from "../simulationTypes";
import { activityParameters, formatParameterDuration, hasTaskConfig } from "./activityParameters";

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
      std: null,
      bounds: null,
      resource: { name: "Legale", amount: 1, costPerHour: 90, calendar: null },
      usesDefault: false,
    });
    expect(params.provenance).toMatchObject({ origin: "manual", confidence: "high" });
    expect(params.provenance.sources).toEqual([{ kind: "interview", id: "steps:s1" }]);
  });

  it("a task at the default duration is not consultant-set", () => {
    const params = activityParameters(REQUEST, "Task_Approve")!;
    expect(params.usesDefault).toBe(true);
    expect(params.std).toEqual({ seconds: 90, assumed: true });
    expect(params.provenance).toMatchObject({ origin: "default", confidence: "low" });
  });

  it("falls back like the backend when the task has no override", () => {
    const params = activityParameters({ ...REQUEST, resources: null, tasks: null }, "Task_X")!;
    expect(params).toMatchObject({
      meanSeconds: 900,
      distribution: "norm",
      resource: { name: "Operatore", amount: 1, costPerHour: 35, calendar: null },
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
    expect(activityParameters({}, "Task_Review")).toBeNull();
  });
  it("knows which elements the run configured as tasks", () => {
    expect(hasTaskConfig(REQUEST, "Task_Review")).toBe(true);
    expect(hasTaskConfig(REQUEST, "Gateway_1")).toBe(false);
    expect(hasTaskConfig(null, "Task_Review")).toBe(false);
  });
  it("reads the explicit spread, bounds and resource calendar of the newer distributions", () => {
    const request = {
      ...REQUEST,
      calendars: [{ id: "cal-night", name: "Turno notte", periods: [] }],
      resources: [{ id: "res-n", name: "Notturno", amount: 2, cost_per_hour: 50, calendar_id: "cal-night" }],
      tasks: [
        { element_id: "L", mean_seconds: 600, distribution: "lognorm", std_seconds: 240, resource_id: "res-n" },
        { element_id: "U", mean_seconds: 600, distribution: "uniform", min_seconds: 300, max_seconds: 900, resource_id: "res-n" },
      ],
    };
    expect(activityParameters(request, "L")).toMatchObject({
      distribution: "lognorm",
      std: { seconds: 240, assumed: false },
      resource: { name: "Notturno", calendar: "Turno notte" },
    });
    expect(activityParameters(request, "U")).toMatchObject({
      distribution: "uniform",
      std: null,
      bounds: { minSeconds: 300, maxSeconds: 900 },
    });
  });
  it("keeps the seconds of a parameter under an hour", () => {
    expect(formatParameterDuration(90, "it")).toBe("1 min 30 s");
    expect(formatParameterDuration(900, "it")).toBe("15 min");
    expect(formatParameterDuration(45, "en")).toBe("45 s");
    expect(formatParameterDuration(5400, "it")).toBe("1h 30 min");
  });
});
