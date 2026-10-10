import { afterEach, describe, expect, it } from "vitest";

import { attributeUsage, caseRuleIssues, sanitizePriorities, toModelPatch, type CaseAttributeDraft } from "./caseRules";
import { loadScenarioDraft } from "./simulationScenario";

const TYPE: CaseAttributeDraft = { id: "attr-1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 20 }, { value: "standard", percent: 80 }] };
const AMOUNT: CaseAttributeDraft = { id: "attr-2", name: "importo", kind: "number", minimum: 100, maximum: 12000 };

describe("case priorities (SIM-12)", () => {
  afterEach(() => window.localStorage.clear());

  it("sends one priority rule per level, level 1 first", () => {
    const patch = toModelPatch([TYPE, AMOUNT], {}, [
      [[{ attributeId: "attr-1", operator: "=", value: "premium" }]],
      [[{ attributeId: "attr-2", operator: ">", value: "5000,5" }]],
    ]);
    expect(patch?.priority_rules).toEqual([
      { level: 1, condition: { any_of: [[{ attribute: "tipo", operator: "=", value: "premium" }]] } },
      { level: 2, condition: { any_of: [[{ attribute: "importo", operator: ">", value: 5000.5 }]] } },
    ]);
    expect(toModelPatch([TYPE], {}, [])).not.toHaveProperty("priority_rules");
  });

  it("blocks the run while a priority is incomplete and keeps its attribute from being removed", () => {
    const incomplete = [[{ attributeId: "attr-2", operator: ">" as const, value: "" }]];
    expect(caseRuleIssues([TYPE, AMOUNT], {}, [incomplete])).toMatchObject({ priorities: 1, ready: false });
    expect(attributeUsage([TYPE, AMOUNT], {}, [incomplete])).toEqual({ "attr-1": 0, "attr-2": 1 });
  });

  it("restores priorities from storage and drops broken ones", () => {
    window.localStorage.setItem("delir-sim-scenario:m1", JSON.stringify({ casePriorities: [
      [[{ attributeId: "attr-1", operator: "=", value: "premium" }]],
      "broken",
      [[{ attributeId: "attr-1", operator: "~", value: "x" }]],
    ] }));
    expect(loadScenarioDraft("m1").casePriorities).toEqual([[[{ attributeId: "attr-1", operator: "=", value: "premium" }]]]);
    expect(sanitizePriorities({})).toEqual([]);
  });
});
