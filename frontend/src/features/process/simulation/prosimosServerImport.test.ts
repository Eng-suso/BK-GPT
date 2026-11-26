import { describe, expect, it } from "vitest";

import { HttpError } from "@/lib/http";

import { cannotFinish, groupNotes, importSummary, prosimosImportSchema, remapProsimosIds } from "./prosimosServerImport";

const result = prosimosImportSchema.parse({
  bpmn_model_id: "m",
  model: {
    activities: [{}, {}, {}],
    pools: [{ resources: [{}, {}] }, { resources: [{}] }],
    gateways: [{}],
    waits: [{}, {}],
  },
  notes: [
    { kind: "info", topic: "instant_activity", message: "a", element_id: "A" },
    { kind: "info", topic: "instant_activity", message: "b", element_id: "B" },
    { kind: "approximated", topic: "missing_branch", message: "c", element_id: "G" },
    { kind: "info", topic: "merge_gateway", message: "d", element_id: null },
  ],
  simod: { model_type: "CRISP" },
});

describe("server import of a Prosimos scenario", () => {
  it("counts what the consultant will simulate", () => {
    expect(importSummary(result)).toEqual({ activities: 3, resources: 3, decisions: 1, waits: 2, fromSimod: true });
  });

  it("groups notes by topic and puts what needs checking first", () => {
    const groups = groupNotes(result.notes);
    expect(groups.map((group) => [group.topic, group.kind, group.notes.length])).toEqual([
      ["missing_branch", "approximated", 1],
      ["instant_activity", "info", 2],
      ["merge_gateway", "info", 1],
    ]);
  });

  it("a warning goes with what needs checking, after what DeliR adjusted", () => {
    const groups = groupNotes([
      { kind: "info", topic: "merge_gateway", message: "d", element_id: null },
      { kind: "warning", topic: "arrivals_faster", message: "w", element_id: null },
      { kind: "approximated", topic: "missing_branch", message: "c", element_id: "G" },
    ]);
    expect(groups.map((group) => [group.topic, group.kind])).toEqual([
      ["missing_branch", "approximated"],
      ["arrivals_faster", "warning"],
      ["merge_gateway", "info"],
    ]);
  });

  it("a plain Prosimos scenario is not presented as discovered by SIMOD", () => {
    expect(importSummary({ ...result, simod: {} }).fromSimod).toBe(false);
  });
});

describe("ids mapped by the consultant", () => {
  it("rename tasks, decisions, branches and waits without touching the original", () => {
    const source = {
      model_type: "CRISP",
      resource_profiles: [{ id: "p", resource_list: [{ id: "r", assignedTasks: ["t1", "t2"] }] }],
      task_resource_distribution: [{ task_id: "t1", resources: [] }, { task_id: "t2", resources: [] }],
      gateway_branching_probabilities: [{ gateway_id: "g", probabilities: [{ path_id: "f1", value: "0.4" }, { path_id: "f2", value: "0.6" }] }],
      event_distribution: [{ event_id: "e" }],
    };
    const mapped = remapProsimosIds(source, {
      tasks: { t1: "T_A" }, gateways: { g: "G_X" }, flows: { "g::f1": "F_1" }, waits: { e: "W_1" },
    });
    expect(mapped).toMatchObject({
      model_type: "CRISP",
      resource_profiles: [{ resource_list: [{ assignedTasks: ["T_A", "t2"] }] }],
      task_resource_distribution: [{ task_id: "T_A" }, { task_id: "t2" }],
      gateway_branching_probabilities: [{ gateway_id: "G_X", probabilities: [{ path_id: "F_1" }, { path_id: "f2" }] }],
      event_distribution: [{ event_id: "W_1" }],
    });
    expect(source.task_resource_distribution[0].task_id).toBe("t1");
  });
});

describe("VAL-01: a process that cannot finish", () => {
  const refusal = (code: string) => new HttpError(400, "Bad Request", {
    ok: false, error: { code, message: "I casi che arrivano a «A» non escono più.", detail: "livelock: gateway G" },
  });

  it("reads the consultant message and the technical detail of the stable code", () => {
    expect(cannotFinish(refusal("process_cannot_finish"))).toEqual({
      message: "I casi che arrivano a «A» non escono più.", detail: "livelock: gateway G",
    });
  });

  it("ignores every other refusal", () => {
    expect(cannotFinish(refusal("bad_request"))).toBeNull();
    expect(cannotFinish(new Error("offline"))).toBeNull();
  });
});
