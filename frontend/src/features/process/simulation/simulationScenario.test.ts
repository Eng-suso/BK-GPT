import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO,
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
    expect(seeded.tasks.Task_A.resourceId).toBe("res-1");
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
  it("stays flat when nothing per-element is set", () => {
    const input = scenarioToInput(structuredClone(DEFAULT_SCENARIO), "<xml/>");
    expect(input.tasks).toBeUndefined();
    expect(input.resources).toBeUndefined();
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
