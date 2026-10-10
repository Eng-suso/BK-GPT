import { describe, expect, it } from "vitest";

import cases from "../../../../../tests/fixtures/simulation/scenario_patch_cases.json";
import { applyScenarioPatch, diffScenario, type ScenarioPatchOp } from "./scenarioPatch";

describe("applyScenarioPatch: gli stessi casi del backend", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const baseline = JSON.parse(JSON.stringify(c.baseline));
    const { draft, conflicts } = applyScenarioPatch(baseline, c.patch as ScenarioPatchOp[]);
    expect(draft).toEqual(c.expected);
    expect(conflicts).toEqual(c.conflicts);
    expect(baseline).toEqual(c.baseline);
  });
});

const AS_IS = {
  scenarioName: "AS-IS",
  totalCases: 100,
  resources: [
    { id: "clerk", name: "Impiegato", amount: 2, costPerHour: 30 },
    { id: "approver", name: "Approvatore", amount: 1, costPerHour: 45 },
  ],
  tasks: { T1: { meanMinutes: 30, resourceId: "clerk" }, T2: { meanMinutes: 20, resourceId: "approver" } },
  calendars: [] as { id: string; name: string }[],
};

describe("diffScenario", () => {
  const roundTrip = (target: object) => {
    const ops = diffScenario(AS_IS, target);
    expect(applyScenarioPatch(AS_IS, ops)).toEqual({ draft: JSON.parse(JSON.stringify(target)), conflicts: [] });
    return ops;
  };

  it("nessuna differenza, nessuna operazione", () => {
    expect(diffScenario(AS_IS, structuredClone(AS_IS))).toEqual([]);
  });

  it("+1 approvatore e' una sola operazione sulla risorsa, per id", () => {
    const target = structuredClone(AS_IS);
    target.resources[1].amount = 2;
    expect(roundTrip(target)).toEqual([{ op: "set", path: ["resources", { id: "approver" }, "amount"], value: 2 }]);
  });

  it("risorse aggiunte, tolte e riordinate", () => {
    const target = { ...AS_IS, resources: [{ id: "bot", name: "Bot", amount: 1, costPerHour: 0 }, AS_IS.resources[0]] };
    const ops = roundTrip(target);
    expect(ops).toContainEqual({ op: "remove", path: ["resources", { id: "approver" }] });
    expect(ops).toContainEqual({ op: "order", path: ["resources"], ids: ["bot", "clerk"] });
  });

  it("una lista vuota che si riempie va per id", () => {
    const target = { ...AS_IS, calendars: [{ id: "cal-1", name: "Turno" }] };
    expect(roundTrip(target)).toEqual([{ op: "set", path: ["calendars", { id: "cal-1" }], value: { id: "cal-1", name: "Turno" } }]);
  });

  it("chiavi nuove, tolte, e valori undefined ignorati", () => {
    const target = { ...AS_IS, warmupCases: 10, sla: undefined, tasks: { T1: AS_IS.tasks.T1 } };
    const ops = roundTrip(target);
    expect(ops).toContainEqual({ op: "set", path: ["warmupCases"], value: 10 });
    expect(ops).toContainEqual({ op: "remove", path: ["tasks", "T2"] });
    expect(ops).toHaveLength(2);
  });

  it("una lista senza id si sostituisce intera", () => {
    const base = { priorities: [{ attribute: "importo" }] };
    const target = { priorities: [{ attribute: "urgenza" }, { attribute: "importo" }] };
    expect(diffScenario(base, target)).toEqual([{ op: "set", path: ["priorities"], value: target.priorities }]);
  });

  it("chi cambia l'AS-IS dopo: la modifica dello scenario resta, il resto segue", () => {
    const target = structuredClone(AS_IS);
    target.resources[1].amount = 2;
    const ops = diffScenario(AS_IS, target);
    const newAsIs = { ...structuredClone(AS_IS), totalCases: 500 };
    newAsIs.resources.unshift({ id: "intern", name: "Stagista", amount: 1, costPerHour: 10 });
    const { draft } = applyScenarioPatch(newAsIs, ops);
    expect(draft.totalCases).toBe(500);
    expect(draft.resources.map((r) => [r.id, r.amount])).toEqual([["intern", 1], ["clerk", 2], ["approver", 2]]);
  });
});
