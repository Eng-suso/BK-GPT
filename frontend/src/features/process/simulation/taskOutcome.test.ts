import { describe, expect, it } from "vitest";

import type { CaseAttributeDraft } from "./caseRules";
import { DEFAULT_SCENARIO, parseScenarioDraft, scenarioParameterIssues, scenarioToInput, type ScenarioDraft, type TaskDraft } from "./simulationScenario";
import { outcomeAttributes, outcomeInput, outcomeIssue, sanitizeOutcome, type OutcomeDraft } from "./taskOutcome";

const BASE: TaskDraft = { meanMinutes: 10, distribution: "norm", resourceId: "clerk" };
const ESITO: OutcomeDraft = { name: "esito", categories: [{ value: "OK", percent: 80 }, { value: "KO", percent: 20 }] };
const KO = [[{ attributeId: "outcome:check", operator: "=" as const, value: "KO" }]];
const TYPE: CaseAttributeDraft = { id: "attr-1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 100 }] };

function draft(tasks: Record<string, Partial<TaskDraft>>, extra: Partial<ScenarioDraft> = {}): ScenarioDraft {
  return {
    ...structuredClone(DEFAULT_SCENARIO),
    resources: [{ id: "clerk", name: "Impiegato", costPerHour: 30, amount: 1, parametersConfirmed: true }],
    tasks: Object.fromEntries(Object.entries(tasks).map(([id, task]) => [id, { ...BASE, ...task }])),
    ...extra,
  };
}

describe("esito dell'attività (SIM-31b)", () => {
  it("manda l'esito con l'attività e le regole a valle sul suo nome, anche senza attributi del caso", () => {
    const input = scenarioToInput(draft(
      { check: { outcome: { ...ESITO, name: " esito " } }, approve: { rework: { backTo: "check", percent: 30, maxRepeats: 2, rule: KO } } },
      { gatewayRules: { G: { F_ko: KO, F_ok: [[{ attributeId: "outcome:check", operator: "=", value: "OK" }]] } } },
    ), null);

    expect(input.tasks?.find((t) => t.elementId === "check")?.outcome).toEqual({
      attribute: "esito", options: [{ value: "OK", probability: 0.8 }, { value: "KO", probability: 0.2 }],
    });
    const rule = { any_of: [[{ attribute: "esito", operator: "=", value: "KO" }]] };
    expect(input.tasks?.find((t) => t.elementId === "approve")?.rework?.condition).toEqual(rule);
    // Senza attributi del caso la patch porta solo le decisioni.
    expect(input.modelPatch).not.toHaveProperty("case_attributes");
    expect(input.modelPatch?.gateways?.[0]?.branches[0]?.condition).toEqual(rule);
  });

  it("normalizza le quote come gli attributi del caso", () => {
    const thirds = { name: "e", categories: [33.3, 33.3, 33.4].map((percent, i) => ({ value: `v${i}`, percent })) };
    const total = outcomeInput(thirds).options.reduce((sum, o) => sum + o.probability, 0);
    expect(total).toBeCloseTo(1, 12);
  });

  it("blocca un esito senza nome, con il nome di un attributo del caso o di un altro esito, o con quote sbagliate", () => {
    const others = outcomeAttributes({ check: { outcome: ESITO }, pay: { outcome: { ...ESITO, name: "pagamento" } } });
    expect(outcomeIssue("check", { ...ESITO, name: " " }, [], others)).toBe("name");
    expect(outcomeIssue("check", { ...ESITO, name: "tipo" }, [TYPE], others)).toBe("duplicateName");
    expect(outcomeIssue("check", { ...ESITO, name: "pagamento" }, [], others)).toBe("duplicateName");
    expect(outcomeIssue("check", { ...ESITO, name: "delir_rework_1" }, [], others)).toBe("reservedName");
    expect(outcomeIssue("check", { ...ESITO, categories: [] }, [], others)).toBe("categories");
    expect(outcomeIssue("check", { ...ESITO, categories: [{ value: "OK", percent: 50 }, { value: "OK", percent: 50 }] }, [], others)).toBe("categoryValue");
    expect(outcomeIssue("check", { ...ESITO, categories: [{ value: "OK", percent: 90 }, { value: "KO", percent: 0 }] }, [], others)).toBe("categorySum");
    expect(outcomeIssue("check", ESITO, [TYPE], others)).toBeNull();
  });

  it("un esito da completare ferma il run, uno pronto no", () => {
    expect(scenarioParameterIssues(draft({ check: { outcome: ESITO } })).outcomes).toBe(0);
    const bad = scenarioParameterIssues(draft({ check: { outcome: { ...ESITO, name: "" } } }));
    expect(bad.outcomes).toBe(1);
    expect(bad.ready).toBe(false);
  });

  it("una regola di salto può leggere l'esito di un'attività prima", () => {
    const issues = scenarioParameterIssues(draft({ check: { outcome: ESITO }, approve: { skip: { percent: 100, rule: KO } } }));
    expect(issues.flowRules).toBe(0);
  });

  it("scarta un esito salvato male senza rompere la bozza", () => {
    expect(sanitizeOutcome("rotto")).toBeUndefined();
    expect(sanitizeOutcome({ name: "esito", categories: [{ value: "OK", percent: "molti" }] })).toBeUndefined();
    const parsed = parseScenarioDraft({ ...draft({ check: {} }), tasks: { check: { ...BASE, outcome: 7 } } });
    expect(parsed.tasks.check?.outcome).toBeUndefined();
  });
});
