import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO,
  newOtherAssignment,
  scenarioParameterIssues,
  scenarioToInput,
  seedDraftFromTemplate,
  taskResourceIds,
  withValidOtherAssignments,
  type ResourceDraft,
  type ScenarioDraft,
  type TaskDraft,
} from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const RESOURCES: ResourceDraft[] = [
  { id: "clerk", name: "Impiegato", costPerHour: 30, amount: 2, parametersConfirmed: true },
  { id: "senior", name: "Senior", costPerHour: 60, amount: 1, parametersConfirmed: true },
  { id: "lead", name: "Responsabile", costPerHour: 90, amount: 1, parametersConfirmed: true },
];

const APPROVE: TaskDraft = {
  meanMinutes: 20,
  distribution: "norm",
  resourceId: "clerk",
  assignmentSource: "manual",
  otherAssignments: [{ resourceId: "senior", meanMinutes: 10, distribution: "fixed" }],
};

const draft = (task: TaskDraft = APPROVE): ScenarioDraft => ({
  ...structuredClone(DEFAULT_SCENARIO),
  resources: RESOURCES,
  tasks: { T_approve: task },
});

describe("other roles of an activity (A2-2)", () => {
  it("sends every other role with its own duration in seconds", () => {
    const [task] = scenarioToInput(draft(), null).tasks ?? [];
    expect(task.resourceId).toBe("clerk");
    expect(task.otherAssignments).toEqual([
      { resourceId: "senior", meanSeconds: 600, distribution: "fixed", stdSeconds: undefined, minSeconds: undefined, maxSeconds: undefined },
    ]);
  });

  it("sends nothing extra when the activity has a single role", () => {
    const [task] = scenarioToInput(draft({ ...APPROVE, otherAssignments: [] }), null).tasks ?? [];
    expect(task).not.toHaveProperty("otherAssignments");
  });

  it("starts a new role from the first free one, with the same duration", () => {
    const next = newOtherAssignment(APPROVE, RESOURCES);
    expect(next).toEqual({ resourceId: "lead", meanMinutes: 20, distribution: "norm", stdMinutes: undefined, minMinutes: undefined, maxMinutes: undefined });
    const full = { ...APPROVE, otherAssignments: [...(APPROVE.otherAssignments ?? []), next!] };
    expect(newOtherAssignment(full, RESOURCES)).toBeNull();
    expect(taskResourceIds(full)).toEqual(["clerk", "senior", "lead"]);
  });

  it("drops a role that no longer exists, repeats one, or became the main role", () => {
    const ids = new Set(["clerk", "senior"]);
    const messy: TaskDraft = {
      ...APPROVE,
      otherAssignments: [
        { resourceId: "clerk", meanMinutes: 5, distribution: "fixed" },
        { resourceId: "ghost", meanMinutes: 5, distribution: "fixed" },
        { resourceId: "senior", meanMinutes: 5, distribution: "fixed" },
        { resourceId: "senior", meanMinutes: 7, distribution: "fixed" },
      ],
    };
    expect(withValidOtherAssignments(messy, ids).otherAssignments).toEqual([{ resourceId: "senior", meanMinutes: 5, distribution: "fixed" }]);
    // Nessun cambiamento: stesso oggetto, niente render inutili.
    expect(withValidOtherAssignments(APPROVE, ids)).toBe(APPROVE);
  });

  it("ignores a malformed list restored from storage", () => {
    const broken = { ...APPROVE, otherAssignments: "senior" } as unknown as TaskDraft;
    expect(withValidOtherAssignments(broken, new Set(["clerk"])).otherAssignments).toBeUndefined();
  });

  it("counts an activity whose other role has a duration to fix", () => {
    const task: TaskDraft = { ...APPROVE, otherAssignments: [{ resourceId: "senior", meanMinutes: 10, distribution: "uniform" }] };
    expect(scenarioParameterIssues(draft(task))).toMatchObject({ durations: 1, ready: false });
  });

  it("keeps the other roles when the BPMN is read again, minus the removed resources", () => {
    const template = { tasks: [{ element_id: "T_approve", name: "Approva", type: "task" }], gateways: [], resources: [] } as unknown as ScenarioTemplate;
    const kept = seedDraftFromTemplate(draft(), template);
    expect(kept.tasks.T_approve.otherAssignments).toEqual(APPROVE.otherAssignments);

    const withoutSenior = seedDraftFromTemplate({ ...draft(), resources: RESOURCES.filter((r) => r.id !== "senior") }, template);
    expect(withoutSenior.tasks.T_approve.otherAssignments).toEqual([]);
  });
});
