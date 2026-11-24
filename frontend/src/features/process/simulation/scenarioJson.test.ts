import { describe, expect, it } from "vitest";

import { DEFAULT_SCENARIO, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import { exportScenarioJson, importScenarioJson } from "./scenarioJson";
import { flowMappingKey } from "./prosimosJson";
import { mergeGatewayIds, prosimosReferenceFields } from "./prosimosReferences";
import { applyNumericJsonMapping, numericJsonFields } from "./scenarioJsonMapping";
import type { ScenarioTemplate } from "./simulationTypes";
import golden from "../../../../../tests/fixtures/simulation/builder_scenarios_golden.json";
import insuranceClaims from "../../../../../tests/fixtures/simulation/insurance_claims_prosimos.json";

const draft: ScenarioDraft = {
  ...DEFAULT_SCENARIO,
  scenarioName: "Claims AS-IS",
  resources: [{ id: "role-1", name: "Advisor", amount: 2, costPerHour: 35, parametersConfirmed: true }],
  tasks: {
    "task-1": { resourceId: "role-1", meanMinutes: 16, distribution: "norm", stdMinutes: 3, minMinutes: 5, maxMinutes: 30 },
  },
  gateways: { "gateway-1": { "flow-1": 60, "flow-2": 40 } },
};

describe("scenario JSON", () => {
  it("imports the Insurance Claims Prosimos file without reducing it to numeric fields", () => {
    const source = insuranceClaims;
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: source.resource_calendars[0].id, name: "Office", periods: [
        { from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" },
      ] },
      tasks: source.task_resource_distribution.map((row) => ({ element_id: row.task_id, name: row.task_id, type: "task" })),
      gateways: source.gateway_branching_probabilities.map((row) => ({
        element_id: row.gateway_id, name: row.gateway_id, type: "exclusiveGateway",
        branches: row.probabilities.map((branch) => ({ flow_id: branch.path_id, flow_name: branch.path_id, target_name: branch.path_id })),
      })),
    };
    const first = importScenarioJson(JSON.stringify(source), "claims", template, draft);
    expect(Object.keys(first.tasks)).toHaveLength(7);
    expect(first.resources).toHaveLength(2);
    expect(first.arrivalIntervalMinutes).toBe(17 / 60);
    const arrivalCalendar = first.calendars?.find((calendar) => calendar.id === first.arrival?.calendarId);
    expect(arrivalCalendar?.periods[0]).toMatchObject({ begin: "09:00:00.074", end: "17:00:00.851" });
    expect(importScenarioJson(JSON.stringify(source), "claims", template, first)).toEqual(first);
  });

  it("round trips every configured distribution parameter idempotently", () => {
    const first = importScenarioJson(exportScenarioJson(draft, "model-1"), "model-1", null);
    const second = importScenarioJson(exportScenarioJson(first, "model-1"), "model-1", null);
    expect(second).toEqual(first);
    expect(second.tasks["task-1"]).toEqual(draft.tasks["task-1"]);
  });

  it("rejects another model and an incomplete Prosimos structure", () => {
    expect(() => importScenarioJson(exportScenarioJson(draft, "model-2"), "model-1", null)).toThrow("altro modello");
    expect(() => importScenarioJson('{"resource_profiles":[],"task_resource_distribution":[]}', "model-1", null)).toThrow("BPMN");
  });

  it("rejects fields that the draft parser would silently discard", () => {
    const file = JSON.parse(exportScenarioJson(draft, "model-1"));
    file.draft.arrival = { distribution: "unsupported", stdMinutes: 4 };
    expect(() => importScenarioJson(JSON.stringify(file), "model-1", null)).toThrow("arrival");
    file.draft.arrival = undefined;
    file.draft.futureParameter = 7;
    expect(() => importScenarioJson(JSON.stringify(file), "model-1", null)).toThrow("futureParameter");
  });

  it("imports the six core Prosimos sections with all four duration parameters", () => {
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "standard", name: "Office", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: [{ element_id: "task-1", name: "Check", type: "task" }],
      gateways: [{ element_id: "gateway-1", name: "Decision", type: "exclusiveGateway", branches: [
        { flow_id: "flow-1", flow_name: "A", target_name: "A" }, { flow_id: "flow-2", flow_name: "B", target_name: "B" },
      ] }],
    };
    const source = {
      resource_profiles: [{ id: "pool", name: "Office", resource_list: [{ id: "role-1", name: "Advisor", cost_per_hour: "35.0", amount: 2, calendar: "standard", assignedTasks: ["task-1"] }] }],
      arrival_time_distribution: { distribution_name: "expon", distribution_params: [{ value: 1800 }, { value: 0 }, { value: 18000 }] },
      arrival_time_calendar: [{ from: "MONDAY", to: "FRIDAY", beginTime: "09:00:00.000", endTime: "17:00:00.000" }],
      gateway_branching_probabilities: [{ gateway_id: "gateway-1", probabilities: [{ path_id: "flow-1", value: "0.6" }, { path_id: "flow-2", value: "0.4" }] }],
      task_resource_distribution: [{ task_id: "task-1", resources: [{ resource_id: "role-1", distribution_name: "norm", distribution_params: [{ value: 960 }, { value: 90 }, { value: 300 }, { value: 1800 }] }] }],
      resource_calendars: [{ id: "standard", name: "Office", time_periods: [{ from: "MONDAY", to: "FRIDAY", beginTime: "09:00:00.000", endTime: "17:00:00.000" }] }],
      batch_processing: [], case_attributes: [],
    };
    const imported = importScenarioJson(JSON.stringify(source), "model-1", template, draft);
    expect(imported.resources[0]).toMatchObject({ id: "role-1", amount: 2, costPerHour: 35 });
    expect(imported.tasks["task-1"]).toMatchObject({ meanMinutes: 16, stdMinutes: 1.5, minMinutes: 5, maxMinutes: 30 });
    expect(imported.gateways["gateway-1"]).toEqual({ "flow-1": 60, "flow-2": 40 });
    expect(imported.arrivalIntervalMinutes).toBe(30);
    expect(scenarioToInput(imported, null).tasks?.[0]).toMatchObject({ meanSeconds: 960, stdSeconds: 90, minSeconds: 300, maxSeconds: 1800 });
    expect(() => importScenarioJson(JSON.stringify({ ...source, case_attributes: [{ name: "tier" }] }), "model-1", template, draft)).toThrow("case_attributes");
  });

  it("imports the repository's Prosimos golden scenario", () => {
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "delir-calendar-standard", name: "Standard office calendar", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: ["T_receive", "T_approve", "T_pay"].map((element_id) => ({ element_id, name: element_id, type: "task" })),
      gateways: [{ element_id: "G", name: "G", type: "exclusiveGateway", branches: [
        { flow_id: "F_high", flow_name: "high", target_name: "high" }, { flow_id: "F_low", flow_name: "low", target_name: "low" },
      ] }],
    };
    const imported = importScenarioJson(JSON.stringify(golden.default), "model-1", template, draft);
    expect(imported.resources).toHaveLength(1);
    expect(Object.keys(imported.tasks)).toHaveLength(3);
    expect(imported.gateways.G).toEqual({ F_high: 50, F_low: 50 });
    expect(scenarioToInput(imported, null).tasks?.[0]).toMatchObject({ meanSeconds: 900, stdSeconds: 90, minSeconds: 630, maxSeconds: 1170 });
  });

  it("imports event distributions for BPMN waits and timers without losing them", () => {
    const source = structuredClone(golden.default) as typeof golden.default & { event_distribution: unknown[] };
    source.event_distribution = [
      { event_id: "W_timer", distribution_name: "norm", distribution_params: [{ value: 600 }, { value: 60 }, { value: 0 }, { value: 3600 }] },
      { event_id: "W_message", distribution_name: "expon", distribution_params: [{ value: 3600 }, { value: 0 }, { value: 86400 }] },
    ];
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "delir-calendar-standard", name: "Standard office calendar", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: ["T_receive", "T_approve", "T_pay"].map((element_id) => ({ element_id, name: element_id, type: "task" })),
      gateways: [{ element_id: "G", name: "G", type: "exclusiveGateway", branches: [
        { flow_id: "F_high", flow_name: "high", target_name: "high" }, { flow_id: "F_low", flow_name: "low", target_name: "low" },
      ] }],
      waits: [
        { element_id: "W_timer", name: "Timer", kind: "timer" },
        { element_id: "W_message", name: "Message", kind: "message" },
      ],
    };
    const imported = importScenarioJson(JSON.stringify(source), "model-1", template, draft);
    expect(imported.waits).toEqual({
      W_timer: { distribution: "norm", meanMinutes: 10, stdMinutes: 1, minMinutes: 0, maxMinutes: 60 },
      W_message: { distribution: "expon", meanMinutes: 60, minMinutes: 0, maxMinutes: 1440 },
    });
    expect(scenarioToInput(imported, null).waits).toMatchObject([
      { elementId: "W_timer", meanSeconds: 600, stdSeconds: 60, minSeconds: 0, maxSeconds: 3600 },
      { elementId: "W_message", meanSeconds: 3600 },
    ]);
    expect(importScenarioJson(JSON.stringify(source), "model-1", template, imported)).toEqual(imported);
    expect(() => importScenarioJson(JSON.stringify({ ...source, event_distribution: [{ event_id: "unknown", distribution_name: "fix", distribution_params: [{ value: 1 }] }] }), "model-1", template, draft)).toThrow("non presente");
  });

  it("never asks to map a point where paths merge back: it has no choice to set (IMP-01)", () => {
    const xml = `<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="P">
      <exclusiveGateway id="G_merge" /><exclusiveGateway id="G_split" /><task id="A" /><task id="B" />
      <sequenceFlow id="f1" sourceRef="A" targetRef="G_merge" /><sequenceFlow id="f2" sourceRef="G_merge" targetRef="G_split" />
      <sequenceFlow id="f3" sourceRef="G_split" targetRef="A" /><sequenceFlow id="f4" sourceRef="G_split" targetRef="B" /></process></definitions>`;
    const merges = mergeGatewayIds(xml);
    expect([...merges]).toEqual(["G_merge"]);
    const template: ScenarioTemplate = { resources: [], tasks: [], gateways: [], waits: [] } as unknown as ScenarioTemplate;
    const source = { gateway_branching_probabilities: [
      { gateway_id: "G_merge", probabilities: [{ path_id: "f2", value: "1" }] },
      { gateway_id: "G_old", probabilities: [{ path_id: "f9", value: "1" }] },
    ] };
    expect(prosimosReferenceFields(source, template, {}, merges).map((field) => field.source)).toEqual(["G_old"]);
    expect(mergeGatewayIds(null).size).toBe(0);
  });

  it("requires explicit mappings for stale timer, decision and branch IDs", () => {
    const source = structuredClone(golden.default) as typeof golden.default & { event_distribution: unknown[] };
    source.event_distribution = [{ event_id: "Event_old", distribution_name: "fix", distribution_params: [{ value: 600 }] }];
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "delir-calendar-standard", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: ["T_receive", "T_approve", "T_pay"].map((element_id) => ({ element_id, name: element_id, type: "task" })),
      gateways: [{ element_id: "G_new", name: "Decision", type: "exclusiveGateway", branches: [
        { flow_id: "F_new_high", flow_name: "high", target_name: "high" },
        { flow_id: "F_new_low", flow_name: "low", target_name: "low" },
      ] }],
      waits: [{ element_id: "Event_new", name: "Timer", kind: "timer" }],
    };
    const fields = prosimosReferenceFields(source, template, {});
    expect(fields.map((field) => field.kind)).toEqual(["gateways", "waits"]);
    expect(() => importScenarioJson(JSON.stringify(source), "model-1", template, draft)).toThrow("Decisione non presente");
    const mapping = {
      gateways: { G: "G_new" }, waits: { Event_old: "Event_new" },
      flows: { [flowMappingKey("G", "F_high")]: "F_new_high", [flowMappingKey("G", "F_low")]: "F_new_low" },
    };
    expect(prosimosReferenceFields(source, template, mapping).map((field) => field.kind)).toEqual(["gateways", "flows", "flows", "waits"]);
    const imported = importScenarioJson(JSON.stringify(source), "model-1", template, draft, mapping);
    expect(imported.gateways.G_new).toEqual({ F_new_high: 50, F_new_low: 50 });
    expect(imported.waits?.Event_new).toEqual({ distribution: "fixed", meanMinutes: 10 });
    expect(() => importScenarioJson(JSON.stringify(source), "model-1", template, draft, { gateways: mapping.gateways, waits: mapping.waits })).toThrow("Flusso non presente");
  });

  it("imports multiple resource profiles without changing task assignments or durations", () => {
    const source = structuredClone(golden.default);
    const originalResource = source.resource_profiles[0].resource_list[0];
    originalResource.assignedTasks = ["T_receive", "T_approve"];
    source.resource_profiles.push({
      id: "second-pool", name: "Payments",
      resource_list: [{ ...originalResource, id: "payments-role", name: "Payment specialist", assignedTasks: ["T_pay"] }],
    });
    source.task_resource_distribution.find((row) => row.task_id === "T_pay")!.resources[0].resource_id = "payments-role";
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "delir-calendar-standard", name: "Standard office calendar", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: ["T_receive", "T_approve", "T_pay"].map((element_id) => ({ element_id, name: element_id, type: "task" })),
      gateways: [{ element_id: "G", name: "G", type: "exclusiveGateway", branches: [
        { flow_id: "F_high", flow_name: "high", target_name: "high" }, { flow_id: "F_low", flow_name: "low", target_name: "low" },
      ] }],
    };
    const imported = importScenarioJson(JSON.stringify(source), "model-1", template, draft);
    expect(imported.resources.map((resource) => resource.id)).toEqual(["delir-resource-operator", "payments-role"]);
    expect(imported.tasks.T_pay.resourceId).toBe("payments-role");
    expect(scenarioToInput(imported, null).tasks?.find((task) => task.elementId === "T_pay")).toMatchObject({ resourceId: "payments-role" });
    expect(importScenarioJson(JSON.stringify(source), "model-1", template, imported)).toEqual(imported);
    source.resource_profiles[1].resource_list[0].id = "delir-resource-operator";
    expect(() => importScenarioJson(JSON.stringify(source), "model-1", template, draft)).toThrow("duplicati");
  });

  it("uses task distributions when assignedTasks metadata is stale", () => {
    const source = structuredClone(golden.default);
    source.resource_profiles[0].resource_list[0].assignedTasks = ["T_receive", "T_approve", "old-task"];
    const template: ScenarioTemplate = {
      resources: [],
      standard_calendar: { id: "delir-calendar-standard", name: "Standard office calendar", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
      tasks: ["T_receive", "T_approve", "T_pay"].map((element_id) => ({ element_id, name: element_id, type: "task" })),
      gateways: [{ element_id: "G", name: "G", type: "exclusiveGateway", branches: [
        { flow_id: "F_high", flow_name: "high", target_name: "high" }, { flow_id: "F_low", flow_name: "low", target_name: "low" },
      ] }],
    };
    const imported = importScenarioJson(JSON.stringify(source), "model-1", template, draft);
    expect(imported.tasks.T_pay.resourceId).toBe("delir-resource-operator");
    expect(importScenarioJson(JSON.stringify(source), "model-1", template, imported)).toEqual(imported);
  });

  it("maps values from a custom JSON only when the user selects their paths and units", () => {
    const fields = numericJsonFields({ simulation: { cases: 120, intervalSeconds: 3600 }, activities: [{ mean: 90 }], staffing: { amount: 4, hourlyCost: "42.5" }, routing: { accepted: 0.7, rejected: 0.3 } });
    expect(fields.map((field) => field.path)).toEqual(["simulation.cases", "simulation.intervalSeconds", "activities[0].mean", "staffing.amount", "staffing.hourlyCost", "routing.accepted", "routing.rejected"]);
    const imported = applyNumericJsonMapping(draft, fields, {
      totalCases: "simulation.cases", arrivalIntervalMinutes: "simulation.intervalSeconds", arrivalUnit: "seconds",
      tasks: { "task-1": "activities[0].mean" }, taskUnit: "seconds",
      resources: { "role-1": { amount: "staffing.amount", costPerHour: "staffing.hourlyCost" } },
      gateways: { "gateway-1": { "flow-1": "routing.accepted", "flow-2": "routing.rejected" } }, probabilityUnit: "fraction",
    });
    expect(imported.totalCases).toBe(120);
    expect(imported.arrivalIntervalMinutes).toBe(60);
    expect(imported.tasks["task-1"].meanMinutes).toBe(1.5);
    expect(imported.tasks["task-1"].stdMinutes).toBe(3);
    expect(imported.resources[0]).toMatchObject({ amount: 4, costPerHour: 42.5, parametersConfirmed: true });
    expect(imported.gateways["gateway-1"]).toEqual({ "flow-1": 70, "flow-2": 30 });
    expect(applyNumericJsonMapping(imported, fields, { totalCases: "simulation.cases" })).toEqual(imported);
  });
});
