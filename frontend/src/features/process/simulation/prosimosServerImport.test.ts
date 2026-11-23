import { describe, expect, it } from "vitest";

import { groupNotes, importSummary, prosimosImportSchema } from "./prosimosServerImport";

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

  it("a plain Prosimos scenario is not presented as discovered by SIMOD", () => {
    expect(importSummary({ ...result, simod: {} }).fromSimod).toBe(false);
  });
});
