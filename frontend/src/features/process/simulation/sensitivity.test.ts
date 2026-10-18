import { describe, expect, it } from "vitest";

import { buildTornado, studyMembers, uncertainFactors, SENSITIVITY_MAX_FACTORS } from "./sensitivity";
import { resolveActiveRun } from "./useSimulationSection";
import type { InputConfidence } from "./simulationProvenance";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";

const field = (confidence: "high" | "medium" | "low") => ({ origin: "default" as const, confidence });

function confidence(activities: Record<string, "high" | "medium" | "low">, gateways: Record<string, "high" | "medium" | "low">, arrival: "high" | "medium" | "low"): InputConfidence {
  return {
    hasDiscovery: true,
    activities: Object.fromEntries(Object.entries(activities).map(([k, c]) => [k, field(c)])),
    gateways: Object.fromEntries(Object.entries(gateways).map(([k, c]) => [k, field(c)])),
    globals: { cases: field("high"), arrival: field(arrival), defaultDuration: field("low") },
    resources: field("high"),
    readiness: { rows: [], overall: "medium", lowConfidenceElementIds: [] },
  };
}

const template = {
  tasks: [
    { element_id: "A", name: "Ricevi", type: "task" },
    { element_id: "B", name: "Verifica", type: "task" },
    { element_id: "C", name: "Approva", type: "task" },
  ],
  gateways: [
    { element_id: "G", name: "Esito", type: "exclusiveGateway", branches: [] },
    { element_id: "R", name: "Importo", type: "exclusiveGateway", branches: [] },
    { element_id: "T", name: "Timer 48h", type: "exclusiveGateway", branches: [], escalation: { activity_id: "C", after_seconds: 172800, normal_flow_id: "f" } },
  ],
  resources: [],
} as unknown as ScenarioTemplate;

const draft = {
  tasks: { A: {}, B: {}, C: {} },
  gateways: { G: { f1: 50, f2: 50 }, R: { f3: 50, f4: 50 }, T: { f5: 90, f6: 10 } },
  gatewayRules: { R: { f3: [[{ attribute: "importo", op: ">", value: "5000" }]] } },
} as unknown as ScenarioDraft;

describe("uncertainFactors", () => {
  it("takes low and medium assumptions, low first, and skips decisions driven by rules or timers", () => {
    const factors = uncertainFactors(confidence({ A: "high", B: "medium", C: "low" }, { G: "low", R: "low", T: "low" }, "medium"), template, draft, "Arrivi");
    expect(factors.map((f) => `${f.kind}:${f.elementId ?? f.label}`)).toEqual(["duration:C", "gateway:G", "duration:B", "arrival:Arrivi"]);
  });

  it("treats an activity whose sources disagree as uncertain, first (SIM-17)", () => {
    const factors = uncertainFactors(confidence({ A: "high", B: "medium", C: "high" }, {}, "high"), template, draft, "Arrivi", new Set(["A"]));
    expect(factors.map((f) => [f.elementId, f.confidence])).toEqual([["A", "low"], ["B", "medium"]]);
  });

  it("caps the study", () => {
    const tasks = Array.from({ length: 12 }, (_, i) => ({ element_id: `T${i}`, name: `T${i}`, type: "task" }));
    const many = { ...template, tasks, gateways: [] } as unknown as ScenarioTemplate;
    const manyDraft = { tasks: Object.fromEntries(tasks.map((t) => [t.element_id, {}])), gateways: {} } as unknown as ScenarioDraft;
    const all = Object.fromEntries(tasks.map((t) => [t.element_id, "low" as const]));
    expect(uncertainFactors(confidence(all, {}, "low"), many, manyDraft, "Arrivi")).toHaveLength(SENSITIVITY_MAX_FACTORS);
  });
});

function run(id: number, request: Record<string, unknown>, cycle?: number, status: SimulationRun["status"] = "completed"): SimulationRun {
  return {
    id,
    status,
    request: { sensitivity_study: "s1", ...request },
    summary: cycle === undefined ? null : { cycle: { avg: cycle }, cost: { perCase: cycle / 100 } },
  } as unknown as SimulationRun;
}

const mark = (kind: string, element_id: string | null, label: string, direction: "low" | "high") => ({ sensitivity: { kind, element_id, label, direction, delta: 0.2 } });

describe("buildTornado", () => {
  const members = [
    run(1, {}, 1000),
    run(2, mark("duration", "B", "Verifica", "low"), 990),
    run(3, mark("duration", "B", "Verifica", "high"), 1005),
    run(4, mark("arrival", null, "Arrivi", "low"), 1600),
    run(5, mark("arrival", null, "Arrivi", "high"), 800),
  ];

  it("sorts assumptions by swing and flags the ones within noise", () => {
    const tornado = buildTornado(members, "cycle");
    expect(tornado.center).toBe(1000);
    expect(tornado.rows.map((r) => [r.label, r.low, r.high, r.swing, r.negligible])).toEqual([
      ["Arrivi", 1600, 800, 800, false],
      ["Verifica", 990, 1005, 15, true],
    ]);
    expect(tornado).toMatchObject({ total: 5, completed: 5, failed: 0, delta: 0.2 });
  });

  it("reads the second KPI from the same runs", () => {
    expect(buildTornado(members, "costPerCase").rows[0].swing).toBeCloseTo(8);
  });

  it("keeps a row without a swing while a variant is still running or failed", () => {
    const partial = [members[0], members[1], run(3, mark("duration", "B", "Verifica", "high"), undefined, "failed")];
    const tornado = buildTornado(partial, "cycle");
    expect(tornado.rows[0]).toMatchObject({ low: 990, high: undefined, swing: 0, negligible: false });
    expect(tornado).toMatchObject({ completed: 2, failed: 1 });
  });

  it("finds the members of the run's study only", () => {
    const other = { ...run(9, {}, 1), request: { sensitivity_study: "s2" } } as SimulationRun;
    expect(studyMembers(members[2], [...members, other]).map((r) => r.id)).toEqual([1, 2, 3, 4, 5]);
    expect(studyMembers(other, members)).toEqual([]);
    expect(studyMembers({ ...members[0], request: {} } as SimulationRun, members)).toEqual([]);
  });
});

describe("default run (SIM-25)", () => {
  it("opens on the newest scenario result, not on a variant", () => {
    const central = run(10, {}, 100);
    const variant = run(11, mark("arrival", null, "Arrivi", "high"), 200);
    expect(resolveActiveRun([variant, central], undefined)?.id).toBe(10);
    expect(resolveActiveRun([variant, central], "11")?.id).toBe(11);
  });
});
