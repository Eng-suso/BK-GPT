import { describe, expect, it } from "vitest";

import { changedElements, comparisonCount, scenarioDeltas, scenarioRuns, scenarioValue, type ScenarioWorkspace, type WorkspaceScenario } from "./scenarioWorkspace";
import type { SimulationRun } from "./simulationTypes";

const scenario = (id: number, kind: WorkspaceScenario["kind"], revision = 1, patch: WorkspaceScenario["patch"] = []): WorkspaceScenario => ({
  id, kind, label: kind === "baseline" ? "AS-IS" : "A", name: kind === "baseline" ? "AS-IS" : "+1", revision,
  draft: {}, patch, conflicts: [], created_at: "", updated_at: "",
});
const AS_IS = scenario(1, "baseline");
const ALT = scenario(2, "alternative");
const WORKSPACE: ScenarioWorkspace = { bpmn_model_id: "m", seed: 7, baseline: AS_IS, alternatives: [ALT] };

let nextId = 100;
const run = (
  scenarioId: number,
  cycle: number,
  { group, index, seed, status = "completed", revision = 1, baselineRevision = 1 }: { group?: string; index?: number; seed?: number; status?: SimulationRun["status"]; revision?: number; baselineRevision?: number } = {},
) => ({
  id: nextId++,
  status,
  request: {
    workspace_scenario: { id: scenarioId, revision, baseline_revision: baselineRevision },
    ...(group ? { replication_group: group, replication_index: index } : {}),
    ...(seed !== undefined ? { seed } : {}),
  },
  summary: status === "completed" ? { cycle: { avg: cycle }, waiting: { avg: cycle / 2 }, cost: { perCase: 10 }, throughputPerHour: 3600 / cycle } : null,
}) as unknown as SimulationRun;

describe("scenarioRuns", () => {
  it("non ancora eseguito", () => {
    expect(scenarioRuns(WORKSPACE, ALT, []).status).toBe("never");
  });

  it("prende l'ultimo run e tutto il suo gruppo", () => {
    const old = run(2, 50);
    const group = [run(2, 40, { group: "g", index: 1 }), run(2, 42, { group: "g", index: 2 })];
    const result = scenarioRuns(WORKSPACE, ALT, [old, ...group, run(1, 60)]);
    expect(result.status).toBe("current");
    expect(result.members.map((r) => r.id)).toEqual(group.map((r) => r.id));
  });

  it("in corso, fallito, e da rifare se lo scenario o l'AS-IS sono cambiati", () => {
    expect(scenarioRuns(WORKSPACE, ALT, [run(2, 0, { status: "pending" })]).status).toBe("pending");
    expect(scenarioRuns(WORKSPACE, ALT, [run(2, 0, { status: "failed" })]).status).toBe("failed");
    expect(scenarioRuns(WORKSPACE, scenario(2, "alternative", 2), [run(2, 40)]).status).toBe("stale");
    const newBaseline = { ...WORKSPACE, baseline: scenario(1, "baseline", 3) };
    expect(scenarioRuns(newBaseline, ALT, [run(2, 40)]).status).toBe("stale");
  });
});

describe("scenarioDeltas", () => {
  it("con le ripetizioni sugli stessi seed: intervallo a coppie, migliore solo se esclude lo zero", () => {
    const runs = [
      ...[100, 110, 105].map((cycle, i) => run(1, cycle, { group: "base", index: i + 1, seed: 7 + i })),
      ...[80, 91, 84].map((cycle, i) => run(2, cycle, { group: "alt", index: i + 1, seed: 7 + i })),
    ];
    const asIs = scenarioRuns(WORKSPACE, AS_IS, runs);
    const alt = scenarioRuns(WORKSPACE, ALT, runs);
    const { kpis, paired } = scenarioDeltas(asIs, alt, runs);
    expect(paired).toBe(true);
    expect(kpis.cycle).toMatchObject({ kind: "interval", paired: true, value: { verdict: "better" } });
    expect(kpis.cycle?.kind === "interval" && kpis.cycle.value.delta).toBeCloseTo(-20, 5);
    // Stesso costo per caso: differenza nulla, quindi non certa.
    expect(kpis.costPerCase).toMatchObject({ value: { verdict: "unclear" } });
    expect(scenarioValue(alt, "cycle")?.interval?.n).toBe(3);
  });

  it("con un run per parte: il delta secco, senza intervallo", () => {
    const runs = [run(1, 100), run(2, 120)];
    const { kpis, paired } = scenarioDeltas(scenarioRuns(WORKSPACE, AS_IS, runs), scenarioRuns(WORKSPACE, ALT, runs), runs);
    expect(paired).toBeNull();
    expect(kpis.cycle).toEqual({ kind: "single", delta: 20, direction: "worse" });
    expect(kpis.throughput).toMatchObject({ kind: "single", direction: "worse" });
  });

  it("niente delta se i due run partono da versioni diverse dell'AS-IS", () => {
    const newBaseline = { ...WORKSPACE, baseline: scenario(1, "baseline", 2) };
    const runs = [
      ...[100, 110, 105].map((cycle, i) => run(1, cycle, { group: "base", index: i + 1, seed: 7 + i, baselineRevision: 2 })),
      ...[80, 91, 84].map((cycle, i) => run(2, cycle, { group: "alt", index: i + 1, seed: 7 + i, baselineRevision: 1 })),
    ];
    const result = scenarioDeltas(scenarioRuns(newBaseline, AS_IS, runs), scenarioRuns(newBaseline, ALT, runs), runs);
    expect(result.mismatch).toBe(true);
    expect(result.kpis.cycle).toBeNull();
  });

  it("niente delta se una delle due parti non ha run completati", () => {
    const runs = [run(1, 100)];
    expect(scenarioDeltas(scenarioRuns(WORKSPACE, AS_IS, runs), scenarioRuns(WORKSPACE, ALT, runs), runs).kpis.cycle).toBeNull();
  });
});

describe("comparisonCount", () => {
  it("conta le alternative con un run sulla stessa versione dell'AS-IS", () => {
    const b = scenario(3, "alternative");
    const c = scenario(4, "alternative");
    const ws = { ...WORKSPACE, alternatives: [ALT, b, c] };
    const runs = [run(1, 100), run(2, 90), run(3, 95, { baselineRevision: 2 }), run(4, 0, { status: "failed" })];
    const asIs = scenarioRuns(ws, AS_IS, runs);
    expect(comparisonCount(asIs, [ALT, b, c].map((s) => scenarioRuns(ws, s, runs)))).toBe(1);
    const more = [...runs, run(4, 92)];
    expect(comparisonCount(scenarioRuns(ws, AS_IS, more), [ALT, b, c].map((s) => scenarioRuns(ws, s, more)))).toBe(2);
  });

  it("il workspace passa il numero di confronti all'intervallo", () => {
    const runs = [
      ...[100, 104, 98].map((cycle, i) => run(1, cycle, { group: "base", index: i + 1, seed: 7 + i })),
      ...[95, 99, 94].map((cycle, i) => run(2, cycle, { group: "alt", index: i + 1, seed: 7 + i })),
    ];
    const one = scenarioDeltas(scenarioRuns(WORKSPACE, AS_IS, runs), scenarioRuns(WORKSPACE, ALT, runs), runs).kpis.cycle;
    const five = scenarioDeltas(scenarioRuns(WORKSPACE, AS_IS, runs), scenarioRuns(WORKSPACE, ALT, runs), runs, 5).kpis.cycle;
    expect(one?.kind === "interval" && five?.kind === "interval" && five.value.half > one.value.half).toBe(true);
    expect(five?.kind === "interval" && five.value.comparisons).toBe(5);
  });
});

describe("changedElements", () => {
  it("le attivita' e le decisioni toccate dalla patch", () => {
    const patch: WorkspaceScenario["patch"] = [
      { op: "set", path: ["tasks", "T1", "meanMinutes"], value: 5 },
      { op: "set", path: ["gateways", "G1", "f1"], value: 30 },
      { op: "set", path: ["resources", { id: "r" }, "amount"], value: 2 },
    ];
    expect([...changedElements({ patch })]).toEqual(["T1", "G1"]);
  });
});
