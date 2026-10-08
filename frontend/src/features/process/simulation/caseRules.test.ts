import { describe, expect, it } from "vitest";

import {
  attributeIssue,
  caseRuleIssues,
  defaultRule,
  ruleIssue,
  ruleSentence,
  sanitizeAttributes,
  sanitizeGatewayRules,
  toModelPatch,
  type CaseAttributeDraft,
} from "./caseRules";
import { DEFAULT_SCENARIO, scenarioToInput, seedDraftFromTemplate } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const tipo: CaseAttributeDraft = { id: "attr-1", name: "Tipo pratica", kind: "category", categories: [{ value: "premium", percent: 30 }, { value: "standard", percent: 70 }] };
const importo: CaseAttributeDraft = { id: "attr-2", name: "importo", kind: "number", minimum: 100, maximum: 12000 };

describe("case attributes", () => {
  it("accepts categories that add up to 100% and numbers with ordered bounds", () => {
    expect(attributeIssue(tipo, [tipo, importo])).toBeNull();
    expect(attributeIssue(importo, [tipo, importo])).toBeNull();
  });

  it("says what is missing", () => {
    expect(attributeIssue({ ...tipo, name: " " }, [tipo])).toBe("name");
    expect(attributeIssue({ ...importo, id: "x", name: "Tipo pratica" }, [tipo])).toBe("duplicateName");
    expect(attributeIssue({ ...tipo, categories: [] }, [tipo])).toBe("categories");
    expect(attributeIssue({ ...tipo, categories: [{ value: "a", percent: 50 }, { value: "a", percent: 50 }] }, [tipo])).toBe("categoryValue");
    expect(attributeIssue({ ...tipo, categories: [{ value: "a", percent: 50 }, { value: "b", percent: 40 }] }, [tipo])).toBe("categorySum");
    expect(attributeIssue({ ...importo, minimum: 5, maximum: 5 }, [importo])).toBe("bounds");
  });
});

describe("branch rules", () => {
  it("needs at least one complete rule per branch, with numbers on numeric attributes", () => {
    const attrs = [tipo, importo];
    expect(ruleIssue([], attrs)).toBe("missingRule");
    expect(ruleIssue([[{ attributeId: "attr-2", operator: ">", value: "" }]], attrs)).toBe("incompleteRule");
    expect(ruleIssue([[{ attributeId: "attr-2", operator: ">", value: "tanto" }]], attrs)).toBe("notANumber");
    expect(ruleIssue([[{ attributeId: "attr-1", operator: ">", value: "premium" }]], attrs)).toBe("incompleteRule");
    expect(ruleIssue([[{ attributeId: "gone", operator: "=", value: "x" }]], attrs)).toBe("unknownAttribute");
    expect(ruleIssue([[{ attributeId: "attr-2", operator: ">", value: "5000,5" }]], attrs)).toBeNull();
  });

  it("counts what blocks the run", () => {
    const rules = { G: { F1: [[{ attributeId: "attr-2", operator: ">" as const, value: "5000" }]], F2: [] } };
    expect(caseRuleIssues([tipo, importo], rules)).toEqual({ attributes: 0, gateways: 1, ready: false });
    expect(caseRuleIssues([tipo, importo], { G: { ...rules.G, F2: [[defaultRule([importo])]] } }).ready).toBe(false);
    expect(caseRuleIssues([tipo, importo], { G: { ...rules.G, F2: [[{ ...defaultRule([importo]), value: "1" }]] } }).ready).toBe(true);
  });

  it("reads like a sentence", () => {
    expect(ruleSentence([[{ attributeId: "attr-2", operator: ">", value: "5000" }, { attributeId: "attr-1", operator: "=", value: "premium" }], [{ attributeId: "attr-1", operator: "!=", value: "standard" }]],
      [tipo, importo], { and: "e", or: "oppure" })).toBe("importo > 5000 e Tipo pratica = premium, oppure Tipo pratica != standard");
  });
});

describe("toModelPatch", () => {
  it("sends nothing when the consultant defined no attribute", () => {
    expect(toModelPatch([], {})).toBeUndefined();
  });

  it("turns the draft into an IR patch with names, normalised weights and typed values", () => {
    const thirds: CaseAttributeDraft = { id: "attr-3", name: "canale", kind: "category", categories: [{ value: "web", percent: 33.3 }, { value: "mail", percent: 33.3 }, { value: "sportello", percent: 33.4 }] };
    const patch = toModelPatch([tipo, importo, thirds], {
      G_split: {
        F_high: [[{ attributeId: "attr-2", operator: ">", value: "5000" }]],
        F_low: [[{ attributeId: "attr-2", operator: "<=", value: "5000" }]],
      },
    });
    expect(patch?.case_attributes?.[0]).toEqual({ name: "Tipo pratica", options: [{ value: "premium", probability: 0.3 }, { value: "standard", probability: 0.7 }], provenance: { origin: "manual" } });
    expect(patch?.case_attributes?.[1]).toEqual({ name: "importo", distribution: { kind: "uniform", minimum: 100, maximum: 12000 }, provenance: { origin: "manual" } });
    const weights = (patch?.case_attributes?.[2] as { options: { probability: number }[] }).options.map((o) => o.probability);
    expect(Math.abs(weights.reduce((a, b) => a + b, 0) - 1)).toBeLessThan(1e-9);
    expect(patch?.gateways?.[0]).toEqual({
      element_id: "G_split",
      branches: [
        { flow_id: "F_high", probability: 0.5, condition: { any_of: [[{ attribute: "importo", operator: ">", value: 5000 }]] }, provenance: { origin: "manual" } },
        { flow_id: "F_low", probability: 0.5, condition: { any_of: [[{ attribute: "importo", operator: "<=", value: 5000 }]] }, provenance: { origin: "manual" } },
      ],
    });
  });
});

describe("scenario draft", () => {
  const template: ScenarioTemplate = {
    tasks: [{ element_id: "T1", name: "Ricevi", type: "task" }],
    gateways: [{ element_id: "G_split", name: "Importo", type: "exclusiveGateway", branches: [
      { flow_id: "F_high", flow_name: "", target_name: "Approva" },
      { flow_id: "F_low", flow_name: "", target_name: "Paga" },
    ] }],
    resources: [],
  } as unknown as ScenarioTemplate;
  const rules = { F_high: [[{ attributeId: "attr-2", operator: ">" as const, value: "5000" }]], F_low: [[{ attributeId: "attr-2", operator: "<=" as const, value: "5000" }]] };

  it("keeps rules only for gateways that still have the same exits", () => {
    const kept = seedDraftFromTemplate({ ...DEFAULT_SCENARIO, gatewayRules: { G_split: rules, G_gone: rules } }, template);
    expect(Object.keys(kept.gatewayRules ?? {})).toEqual(["G_split"]);
    const changed = seedDraftFromTemplate({ ...DEFAULT_SCENARIO, gatewayRules: { G_split: { F_high: rules.F_high } } }, template);
    expect(changed.gatewayRules).toEqual({});
  });

  it("puts the patch on the run request", () => {
    const input = scenarioToInput({ ...DEFAULT_SCENARIO, caseAttributes: [importo], gatewayRules: { G_split: rules } }, null);
    expect(input.modelPatch?.gateways?.[0].element_id).toBe("G_split");
    expect(scenarioToInput(DEFAULT_SCENARIO, null).modelPatch).toBeUndefined();
  });

  it("drops stored drafts that do not fit", () => {
    expect(sanitizeAttributes([tipo, { id: 1 }, { ...importo, minimum: "x" }])).toEqual([tipo]);
    expect(sanitizeGatewayRules({ G: { F1: [[{ attributeId: "a", operator: "~", value: "1" }]], F2: rules.F_low } })).toEqual({ G: { F2: rules.F_low } });
  });
});
