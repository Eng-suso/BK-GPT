import { describe, expect, it } from "vitest";

import type { CaseAttributeDraft } from "./caseRules";
import { DEFAULT_SCENARIO, loadScenarioDraft, saveScenarioDraft, scenarioParameterIssues, scenarioToInput } from "./simulationScenario";
import { newSlaSegment, sanitizeSlaSegments, slaSegmentIssues, slaSegmentsInput, type SlaSegmentDraft } from "./slaSegments";

const TIPO: CaseAttributeDraft = { id: "a1", name: " tipo ", kind: "category", categories: [{ value: "premium", percent: 20 }, { value: "standard", percent: 80 }] };
const IMPORTO: CaseAttributeDraft = { id: "a2", name: "importo", kind: "number", minimum: 100, maximum: 1000 };
const GOAL = { target: 2, unit: "days", sharePercent: 90 } as const;
const premium: SlaSegmentDraft = { attributeId: "a1", value: "premium", target: 24, unit: "hours", sharePercent: 95 };

describe("service objectives by group of cases (SIM-13b)", () => {
  it("proposes the next category without an objective, only from category attributes", () => {
    expect(newSlaSegment([IMPORTO], [], GOAL)).toBeNull();
    expect(newSlaSegment([IMPORTO, TIPO], [], GOAL)).toEqual({ attributeId: "a1", value: "premium", ...GOAL });
    expect(newSlaSegment([TIPO], [premium], GOAL)?.value).toBe("standard");
    expect(newSlaSegment([TIPO], [premium, { ...premium, value: "standard" }], GOAL)).toBeNull();
  });

  it("flags a removed category, a repeated group and an invalid goal", () => {
    expect(slaSegmentIssues([premium], [TIPO])).toEqual([null]);
    expect(slaSegmentIssues([{ ...premium, value: "gold" }], [TIPO])).toEqual(["attribute"]);
    expect(slaSegmentIssues([premium], [])).toEqual(["attribute"]);
    expect(slaSegmentIssues([premium, premium], [TIPO])).toEqual([null, "duplicate"]);
    expect(slaSegmentIssues([{ ...premium, target: 0 }], [TIPO])).toEqual(["target"]);
    expect(slaSegmentIssues([{ ...premium, sharePercent: 120 }], [TIPO])).toEqual(["share"]);
  });

  it("sends the attribute by the name the engine writes in the log", () => {
    expect(slaSegmentsInput([premium], [TIPO])).toEqual([{ attribute: "tipo", value: "premium", targetSeconds: 86_400, share: 0.95 }]);
    const draft = { ...structuredClone(DEFAULT_SCENARIO), caseAttributes: [TIPO], sla: { ...GOAL, segments: [premium] } };
    expect(scenarioToInput(draft, null).sla).toEqual({
      targetSeconds: 172_800, share: 0.9, segments: [{ attribute: "tipo", value: "premium", targetSeconds: 86_400, share: 0.95 }],
    });
    expect(scenarioParameterIssues(draft).sla).toBe(false);
    expect(scenarioParameterIssues({ ...draft, caseAttributes: [] }).sla).toBe(true);
  });

  it("keeps the groups in the saved draft and drops malformed ones", () => {
    expect(sanitizeSlaSegments([premium, { attributeId: "a1" }, null, { ...premium, unit: "weeks" }])).toEqual([
      premium, { ...premium, unit: "days" },
    ]);
    expect(sanitizeSlaSegments([])).toBeUndefined();
    const draft = { ...structuredClone(DEFAULT_SCENARIO), caseAttributes: [TIPO], sla: { ...GOAL, segments: [premium] } };
    saveScenarioDraft("model-sla-seg", draft);
    expect(loadScenarioDraft("model-sla-seg")?.sla?.segments).toEqual([premium]);
  });
});
