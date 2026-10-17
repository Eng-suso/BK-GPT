import { describe, expect, it } from "vitest";

import type { CaseAttributeDraft } from "./caseRules";
import { flowRuleAttributeIds, reworkIssue, skipIssue } from "./flowRules";
import { DEFAULT_SCENARIO, parseScenarioDraft, scenarioParameterIssues, scenarioToInput, type ScenarioDraft, type TaskDraft } from "./simulationScenario";

const AMOUNT: CaseAttributeDraft = { id: "attr-1", name: "importo", kind: "number", minimum: 100, maximum: 12000 };
const SMALL = [[{ attributeId: "attr-1", operator: "<" as const, value: "1000" }]];
const BASE: TaskDraft = { meanMinutes: 10, distribution: "norm", resourceId: "clerk" };
const ACTIVITIES = new Set(["receive", "approve"]);

function draft(approve: Partial<TaskDraft>): ScenarioDraft {
  return {
    ...structuredClone(DEFAULT_SCENARIO),
    resources: [{ id: "clerk", name: "Impiegato", costPerHour: 30, amount: 1, parametersConfirmed: true }],
    caseAttributes: [AMOUNT],
    tasks: { receive: BASE, approve: { ...BASE, ...approve } },
  };
}

describe("salto e rilavorazione (SIM-35)", () => {
  it("manda la quota come probabilità e la regola come condizione dell'IR", () => {
    const input = scenarioToInput(draft({
      skip: { percent: 30, rule: SMALL },
      rework: { backTo: "receive", percent: 25, maxRepeats: 2 },
    }), null);
    const approve = input.tasks?.find((t) => t.elementId === "approve");
    expect(approve?.skip).toEqual({ probability: 0.3, condition: { any_of: [[{ attribute: "importo", operator: "<", value: 1000 }]] } });
    expect(approve?.rework).toEqual({ backTo: "receive", probability: 0.25, maxRepeats: 2 });
    expect(input.tasks?.find((t) => t.elementId === "receive")).not.toHaveProperty("skip");
  });

  it("blocca il run con una quota fuori scala, un ritorno senza meta o una regola incompleta", () => {
    expect(skipIssue({ percent: 0 }, [AMOUNT])).toBe("skipPercent");
    expect(skipIssue({ percent: 100 }, [AMOUNT])).toBeNull();
    expect(skipIssue({ percent: 50, rule: [[{ attributeId: "attr-1", operator: "<", value: "" }]] }, [AMOUNT])).toBe("rule");
    expect(reworkIssue({ backTo: "receive", percent: 100, maxRepeats: 1 }, [AMOUNT], ACTIVITIES)).toBe("reworkPercent");
    expect(reworkIssue({ backTo: "gone", percent: 20, maxRepeats: 1 }, [AMOUNT], ACTIVITIES)).toBe("reworkTarget");
    expect(reworkIssue({ backTo: "receive", percent: 20, maxRepeats: 11 }, [AMOUNT], ACTIVITIES)).toBe("reworkRepeats");
    expect(reworkIssue({ backTo: "receive", percent: 20, maxRepeats: 3 }, [AMOUNT], ACTIVITIES)).toBeNull();

    const issues = scenarioParameterIssues(draft({ rework: { backTo: "gone", percent: 20, maxRepeats: 1 } }));
    expect(issues.flowRules).toBe(1);
    expect(issues.ready).toBe(false);
  });

  it("conta gli attributi che le regole usano, così non si tolgono", () => {
    expect(flowRuleAttributeIds([{ skip: { percent: 10, rule: SMALL } }, { rework: { backTo: "x", percent: 5, maxRepeats: 1 } }])).toEqual(["attr-1"]);
  });

  it("scarta da una bozza salvata un salto o un ritorno che non tornano", () => {
    const parsed = parseScenarioDraft({ tasks: { approve: { ...BASE, skip: { percent: "tanto" }, rework: { backTo: "receive", percent: 20, maxRepeats: 2, rule: "x" } } } });
    expect(parsed.tasks.approve.skip).toBeUndefined();
    expect(parsed.tasks.approve.rework).toEqual({ backTo: "receive", percent: 20, maxRepeats: 2 });
  });
});
