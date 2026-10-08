import { describe, expect, it } from "vitest";

import type { ScenarioElementProvenance, ScenarioTemplate } from "../simulationTypes";
import { durationView, elementFromModel, STANDARD_CALENDAR_ID } from "./modelParameters";
import type { RunModel } from "./runModel";

const MODEL: RunModel = {
  calendars: [
    { id: STANDARD_CALENDAR_ID, name: "Standard office calendar", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00:00.000", end: "17:00:00.000" }] },
    { id: "night", name: "Notte", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "22:00:00", end: "23:59:59" }] },
  ],
  pools: [
    {
      id: "p",
      name: "Ufficio",
      resources: [
        { id: "ops", name: "Operatore", cost_per_hour: 30, amount: 2, calendar_id: STANDARD_CALENDAR_ID },
        { id: "night-ops", name: "Notturno", cost_per_hour: 45, amount: 1, calendar_id: "night" },
      ],
    },
  ],
  activities: [
    {
      element_id: "Task_A",
      name: "Verifica",
      assignments: [
        { resource_id: "ops", duration: { kind: "lognormal", mean: 600, variance: 90000, minimum: 60, maximum: 3600 }, provenance: { origin: "manual", sources: [] } },
        { resource_id: "night-ops", duration: { kind: "uniform", minimum: 300, maximum: 900 }, provenance: null },
      ],
    },
    {
      element_id: "Task_B",
      name: "Approva",
      assignments: [
        { resource_id: "ops", duration: { kind: "normal", mean: 900, std: 90, minimum: 630, maximum: 1170 }, provenance: { origin: "observed", confidence: "high", sources: [{ kind: "event_log", id: "log-7", label: "Export SAP" }] } },
      ],
    },
  ],
  gateways: [
    {
      element_id: "Gw",
      branches: [
        { flow_id: "f1", probability: 0.5, condition: { any_of: [[{ attribute: "importo", operator: ">", value: 5000 }]] }, provenance: { origin: "manual", sources: [] } },
        { flow_id: "f2", probability: 0.5, condition: { any_of: [[{ attribute: "importo", operator: "<=", value: 5000 }]] }, provenance: { origin: "manual", sources: [] } },
      ],
    },
  ],
};

const DECLARED: ScenarioElementProvenance = {
  element_id: "Task_A",
  kind: "activity",
  name: "Verifica",
  parameter: "duration",
  provenance: { origin: "declared", confidence: "high", sources: [{ kind: "interview", id: "steps:s1" }] },
  confidence: "high",
  evidence: [],
  open_questions: 0,
  hint_ref: null,
};

const TEMPLATE: ScenarioTemplate = {
  tasks: [],
  gateways: [{ element_id: "Gw", name: "Importo?", type: "exclusiveGateway", branches: [
    { flow_id: "f1", flow_name: "Sopra soglia", target_name: "Seconda firma" },
    { flow_id: "f2", flow_name: "", target_name: "Pagamento" },
  ] }],
};

describe("elementFromModel", () => {
  it("shows every assignment of an activity with resource, calendar and full parameters", () => {
    const view = elementFromModel(MODEL, "Task_A", DECLARED);
    expect(view?.kind).toBe("activity");
    if (view?.kind !== "activity") return;
    const [first, second] = view.assignments;
    expect(first.resource).toMatchObject({ name: "Operatore", amount: 2, costPerHour: 30, calendar: { standard: true } });
    expect(first.duration).toEqual({ kind: "lognormal", meanSeconds: 600, stdSeconds: 300, minSeconds: 60, maxSeconds: 3600 });
    expect(first.provenance).toMatchObject({ origin: "manual", confidence: "high" });
    expect(first.provenance.sources).toEqual([{ kind: "interview", id: "steps:s1" }]);
    expect(second.resource?.calendar).toEqual({ standard: false, name: "Notte", periods: [{ fromDay: "MONDAY", toDay: "FRIDAY", begin: "22:00", end: "23:59" }] });
    // Nessuna provenienza nell'IR: e' un'assunzione su una struttura dichiarata.
    expect(second.provenance).toMatchObject({ origin: "estimated", confidence: "medium" });
  });

  it("keeps an observed origin and its event log source", () => {
    const view = elementFromModel(MODEL, "Task_B");
    if (view?.kind !== "activity") throw new Error("activity expected");
    expect(view.assignments[0].provenance).toMatchObject({ origin: "observed", confidence: "high" });
    expect(view.assignments[0].provenance.sources?.[0]).toMatchObject({ kind: "event_log", label: "Export SAP" });
  });

  it("shows the branches of a gateway with their rules and readable names", () => {
    const view = elementFromModel(MODEL, "Gw", undefined, TEMPLATE);
    if (view?.kind !== "gateway") throw new Error("gateway expected");
    expect(view.branches.map((b) => b.label)).toEqual(["Sopra soglia", "Pagamento"]);
    expect(view.branches[0].condition).toEqual([[{ attribute: "importo", operator: ">", value: 5000 }]]);
    expect(view.provenance.origin).toBe("manual");
    expect(view.branches[0].provenance.origin).toBe("manual");
  });

  it("returns null for an element the model does not simulate", () => {
    expect(elementFromModel(MODEL, "StartEvent_1")).toBeNull();
  });
});

describe("durationView", () => {
  it("gives the exponential no spread of its own and the fixed a single value", () => {
    expect(durationView({ kind: "exponential", mean: 60, minimum: 0, maximum: 600 })).toMatchObject({ stdSeconds: null });
    expect(durationView({ kind: "fixed", value: 120 })).toEqual({ kind: "fixed", valueSeconds: 120 });
  });
});
