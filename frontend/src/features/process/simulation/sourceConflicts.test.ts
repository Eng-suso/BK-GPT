import { describe, expect, it } from "vitest";

import { realProcessingByElement } from "./eventlog/realVsSimulated";
import type { EventLogSummary } from "./eventlog/eventLogTypes";
import { sourceConflicts } from "./sourceConflicts";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationClaims } from "./simulationTypes";

const template = {
  tasks: [
    { element_id: "A", name: "Ricevi", type: "task" },
    { element_id: "B", name: "Verifica", type: "task" },
    { element_id: "C", name: "Paga", type: "task" },
  ],
  gateways: [],
} as unknown as ScenarioTemplate;

const draft = {
  defaultTaskMinutes: 15,
  tasks: {
    A: { meanMinutes: 15, distribution: "norm" },
    B: { meanMinutes: 30, distribution: "norm" },
    C: { meanMinutes: 15, distribution: "uniform", minMinutes: 10, maxMinutes: 30 },
  },
  gateways: {},
  dismissedClaims: { C: [3] },
} as unknown as ScenarioDraft;

const proposal = (claim_id: number, source_name: string, seconds: number | null) => ({
  claim_id, statement: "", quote: "", quote_verified: true, source_id: "s", source_name, score: 1, match: "lexical",
  duration_hint: seconds === null ? null : { text: "", seconds },
});
const claims = { sources: 2, activities: [
  { element_id: "A", name: "Ricevi", proposals: [proposal(1, "Procedure.pdf", 600)] },
  { element_id: "B", name: "Verifica", proposals: [proposal(2, "Intervista Rossi", 1200), proposal(4, "Mail", null)] },
  { element_id: "C", name: "Paga", proposals: [proposal(3, "Vecchio manuale", 4000)] },
] } as unknown as SimulationClaims;

const args = { template, draft, claims, logName: "Log 2025", panelLabel: "Pannello" };

describe("sourceConflicts (SIM-17)", () => {
  it("turns sources more than 25% apart into a conflict, widest first", () => {
    const real = new Map([["A", { seconds: 1200 }], ["B", { seconds: 1700 }], ["C", { seconds: 1250 }]]);
    const conflicts = sourceConflicts({ ...args, realProcessing: real });
    expect(conflicts.map((c) => c.elementId)).toEqual(["A", "B"]);
    expect(conflicts[0]).toMatchObject({ shortest: { kind: "claim", label: "Procedure.pdf" }, longest: { kind: "log", label: "Log 2025" }, spread: 1 });
    expect(conflicts[1].sources.map((s) => s.kind)).toEqual(["panel", "claim", "log"]);
  });

  it("ignores a default value, a dismissed claim and a claim without a duration", () => {
    // A: il valore predefinito non conta, resta una sola fonte. C: l'affermazione e' scartata.
    expect(sourceConflicts({ ...args, realProcessing: null }).map((c) => c.elementId)).toEqual(["B"]);
  });

  it("uses the midpoint of a uniform duration set in the panel", () => {
    const moved = { ...draft, tasks: { ...draft.tasks, C: { ...draft.tasks.C, meanMinutes: 16 } } } as ScenarioDraft;
    const [conflict] = sourceConflicts({ ...args, draft: moved, realProcessing: new Map([["C", { seconds: 2000 }]]) });
    expect(conflict.shortest).toMatchObject({ kind: "panel", seconds: 1200 });
  });
});

describe("realProcessingByElement", () => {
  it("weighs log activities on the same element by executions and skips complete-only logs", () => {
    const summary = { timing: "start_and_end", byActivity: [
      { el: "A", count: 3, processing: { avg: 100 } },
      { el: "A", count: 1, processing: { avg: 500 } },
      { el: null, count: 9, processing: { avg: 1 } },
    ] } as unknown as EventLogSummary;
    expect(realProcessingByElement(summary).get("A")).toEqual({ seconds: 200, count: 4 });
    expect(realProcessingByElement({ ...summary, timing: "complete_only" }).size).toBe(0);
  });
});
