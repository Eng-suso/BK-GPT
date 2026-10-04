import { afterEach, describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO,
  loadScenarioDraft,
  saveScenarioDraft,
  scenarioResourceIssues,
  scenarioToInput,
  seedDraftFromTemplate,
  type ScenarioDraft,
} from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE: ScenarioTemplate = {
  tasks: [
    { element_id: "Task_A", name: "Ricevi", type: "userTask" },
    { element_id: "Task_B", name: "Approva", type: "serviceTask" },
  ],
  gateways: [
    {
      element_id: "Gw_1",
      name: "Esito",
      type: "exclusiveGateway",
      branches: [
        { flow_id: "f_ok", flow_name: "ok", target_name: "Approva" },
        { flow_id: "f_ko", flow_name: "ko", target_name: "Rifiuta" },
      ],
    },
  ],
};

describe("seedDraftFromTemplate", () => {
  it("fills defaults for every template element", () => {
    const seeded = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    expect(Object.keys(seeded.tasks)).toEqual(["Task_A", "Task_B"]);
    expect(seeded.tasks.Task_A.meanMinutes).toBe(DEFAULT_SCENARIO.defaultTaskMinutes);
    expect(seeded.tasks.Task_A.resourceId).toBe("");
    expect(seeded.resources).toEqual([]);
    const branches = seeded.gateways.Gw_1;
    expect(Object.keys(branches)).toEqual(["f_ok", "f_ko"]);
    expect(branches.f_ok + branches.f_ko).toBe(100);
  });

  it("keeps existing edits and drops stale elements", () => {
    const edited: ScenarioDraft = {
      ...structuredClone(DEFAULT_SCENARIO),
      tasks: {
        Task_A: { meanMinutes: 42, distribution: "fixed", resourceId: "res-1" },
        Task_GONE: { meanMinutes: 5, distribution: "norm", resourceId: "res-1" },
      },
      gateways: { Gw_1: { f_ok: 70, f_ko: 30 } },
    };
    const seeded = seedDraftFromTemplate(edited, TEMPLATE);
    expect(seeded.tasks.Task_A.meanMinutes).toBe(42);
    expect(seeded.tasks.Task_GONE).toBeUndefined();
    expect(seeded.gateways.Gw_1).toEqual({ f_ok: 70, f_ko: 30 });
  });
});

describe("scenarioToInput", () => {
  it("always sends explicit resources so an empty draft cannot invoke legacy defaults", () => {
    const input = scenarioToInput(structuredClone(DEFAULT_SCENARIO), "<xml/>");
    expect(input.tasks).toEqual([]);
    expect(input.resources).toEqual([]);
    expect(input.defaultTaskDurationSeconds).toBe(15 * 60);
  });

  it("emits structured overrides once configured", () => {
    const seeded = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    seeded.tasks.Task_A = { meanMinutes: 20, distribution: "expon", resourceId: "res-1" };
    const input = scenarioToInput(seeded, "<xml/>");
    expect(input.tasks).toHaveLength(2);
    const a = input.tasks?.find((task) => task.elementId === "Task_A");
    expect(a?.meanSeconds).toBe(1200);
    expect(a?.distribution).toBe("expon");
    expect(input.gateways?.[0].branches[0].probability).toBeCloseTo(0.5);
  });
});

const lane = { id: "bpmn-lane-demo", bpmn_id: "Lane_demo", name: "Operations", kind: "lane" as const,
  pool_name: "Company", parent_name: null, task_ids: ["Task_A"] };

describe("resource membership and confirmation", () => {
  afterEach(() => localStorage.clear());
  it("uses exact lane membership, leaving tasks outside lanes unassigned", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), { ...TEMPLATE, resources: [lane] });
    expect(draft.resources[0].source).toEqual(lane);
    expect(draft.resources[0].parametersConfirmed).toBe(false);
    expect(draft.tasks.Task_A.resourceId).toBe(lane.id);
    expect(draft.tasks.Task_B.resourceId).toBe("");
    expect(scenarioResourceIssues(draft)).toMatchObject({ pending: 1, unassigned: 1, ready: false });
    draft.resources[0].parametersConfirmed = true;
    draft.tasks.Task_B.resourceId = lane.id;
    expect(scenarioResourceIssues(draft).ready).toBe(true);
  });
  it("preserves manual assignments, edits, and intentionally removed model candidates", () => {
    const draft = seedDraftFromTemplate({ ...structuredClone(DEFAULT_SCENARIO), excludedResourceIds: [lane.id],
      resources: [{ id: "manual", name: "Support", amount: 2, costPerHour: 40, parametersConfirmed: true }],
      tasks: { Task_A: { meanMinutes: 30, distribution: "fixed", resourceId: "manual" } },
    }, { ...TEMPLATE, resources: [lane] });
    expect(draft.resources).toHaveLength(1);
    expect(draft.tasks.Task_A.resourceId).toBe("manual");
    expect(draft.tasks.Task_B.resourceId).toBe("");
  });
  it("does not replace an invalid resource with the first manual role", () => {
    const draft = seedDraftFromTemplate({ ...structuredClone(DEFAULT_SCENARIO),
      resources: [{ id: "manual", name: "Support", amount: 1, costPerHour: 0 }],
      tasks: { Task_A: { meanMinutes: 10, distribution: "fixed", resourceId: "deleted" } },
    }, TEMPLATE);
    expect(draft.tasks.Task_A.resourceId).toBe("");
    expect(scenarioToInput(draft, null).tasks?.[0].resourceId).toBe("");
  });
  it("migrates only the pristine old operator and preserves custom or confirmed resources", () => {
    const draft = { ...structuredClone(DEFAULT_SCENARIO), resources: [{ id: "res-1", name: "Operatore", amount: 1, costPerHour: 35 }] };
    saveScenarioDraft("legacy", draft);
    expect(loadScenarioDraft("legacy").resources).toEqual([]);
    saveScenarioDraft("explicit", { ...draft, resources: [{ ...draft.resources[0], parametersConfirmed: true }] });
    expect(loadScenarioDraft("explicit").resources).toHaveLength(1);
    saveScenarioDraft("custom", { ...draft, resources: [{ ...draft.resources[0], name: "Finance" }] });
    expect(loadScenarioDraft("custom").resources[0].name).toBe("Finance");
    saveScenarioDraft("mixed", { ...draft, resources: [...draft.resources, { id: "res-2", name: "Finance", amount: 2, costPerHour: 40 }] });
    expect(loadScenarioDraft("mixed").resources).toHaveLength(1);
    expect(loadScenarioDraft("mixed").resources[0].name).toBe("Finance");
    expect(loadScenarioDraft("mixed").resources[0].parametersConfirmed).toBe(false);
    saveScenarioDraft("empty", structuredClone(DEFAULT_SCENARIO));
    expect(loadScenarioDraft("empty").resources).toEqual([]);
  });
  it("rejects non-finite costs, fractional capacity and pending confirmations", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), { ...TEMPLATE, resources: [{ ...lane, task_ids: ["Task_A", "Task_B"] }] });
    draft.resources[0] = { ...draft.resources[0], parametersConfirmed: true, amount: 1.5 };
    expect(scenarioResourceIssues(draft).ready).toBe(false);
    draft.resources[0] = { ...draft.resources[0], amount: 2, costPerHour: NaN };
    expect(scenarioResourceIssues(draft).ready).toBe(false);
  });
  it("follows updated BPMN membership while preserving explicit consultant overrides", () => {
    const first = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), { ...TEMPLATE, resources: [lane] });
    const nextLane = { ...lane, id: "bpmn-other", bpmn_id: "Lane_other", name: "Finance", task_ids: ["Task_A", "Task_B"] };
    const updated = seedDraftFromTemplate(first, { ...TEMPLATE, resources: [nextLane] });
    expect(updated.tasks.Task_A.resourceId).toBe(nextLane.id);
    expect(updated.resources.find((r) => r.id === lane.id)?.source).toBeUndefined();
    first.resources.push({ id: "manual", name: "Support", amount: 2, costPerHour: 0, parametersConfirmed: true });
    first.tasks.Task_A = { ...first.tasks.Task_A, resourceId: "manual", assignmentSource: "manual" };
    expect(seedDraftFromTemplate(first, { ...TEMPLATE, resources: [nextLane] }).tasks.Task_A.resourceId).toBe("manual");
  });

});
