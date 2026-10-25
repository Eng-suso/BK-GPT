import { describe, expect, it } from "vitest";

import { i18n } from "@/lib/i18n";

import { decisionRecordHtml, type DecisionRecordInput } from "./decisionRecord";
import type { ScenarioRuns } from "./scenarioWorkspace";
import type { SimulationRun } from "./simulationTypes";

const t = i18n.getFixedT("it", "process") as unknown as (key: string, options?: Record<string, unknown>) => string;

const completed = (id: number, cycle: number) => ({
  id, status: "completed", request: {}, summary: { cycle: { avg: cycle }, waiting: { avg: 600 }, cost: { perCase: 50 }, throughputPerHour: 2 },
}) as unknown as SimulationRun;
const results = (run: SimulationRun): ScenarioRuns => ({ latest: run, members: [run], completed: [run], status: "current", bpmnChanged: false });

function input(overrides: Partial<DecisionRecordInput> = {}): DecisionRecordInput {
  return {
    processName: "Ciclo passivo",
    generatedAt: new Date("2026-10-18T10:00:00Z"),
    seed: 7,
    asIs: { name: "AS-IS", results: results(completed(1, 7200)) },
    alternative: { name: "A · Secondo approvatore", results: results(completed(2, 3600)), changes: ["Approvatore · Unità: 1 → 2"] },
    deltas: { kpis: { cycle: { kind: "single", delta: -3600, direction: "better" }, waiting: null, costPerCase: null, throughput: null }, paired: null, mismatch: false },
    comparisons: 1,
    readiness: { rows: [{ key: "durations", pct: 60, confidence: "medium", flagged: 2 }], overall: "medium", lowConfidenceElementIds: [] },
    uncertain: [{ name: "Approva", confidence: "low", origin: "default" }],
    conflicts: [{ elementId: "B", name: "Verifica", spread: 1, sources: [],
      shortest: { kind: "log", label: "sap.csv", seconds: 600 }, longest: { kind: "claim", label: "<script>x</script>.pdf", seconds: 1200 } }],
    tornado: null,
    ...overrides,
  };
}

describe("decision record (SIM-27)", () => {
  it("puts changes, results, assumptions and risks in one printable page", () => {
    const html = decisionRecordHtml(input(), t, "it");
    expect(html).toMatch(/^<!doctype html>/);
    expect(html).toContain("<title>Decision record · A · Secondo approvatore</title>");
    expect(html).toContain("Approvatore · Unità: 1 → 2");
    expect(html).toContain("senza intervallo");
    expect(html).toContain("Un run per parte: la differenza non ha intervallo");
    expect(html).toContain("Approva: ");
    expect(html).toContain("Una sola simulazione per scenario");
    expect(html).toContain("Prontezza complessiva media");
    expect(html).toContain("Nessuno studio di sensitività su questo scenario");
    expect(html).toContain("Quale vale, e per quali casi?");
  });

  it("adds the text written for the client, escaped and said to come from the AI (SIM-24b)", () => {
    const html = decisionRecordHtml(input({ narrative: "Un caso dura −1 h in meno <b>subito</b>." }), t, "it");
    expect(html).toContain("Testo per il cliente.</b> Un caso dura −1 h in meno &lt;b&gt;subito&lt;/b&gt;.");
    expect(html).toContain("Redatto dall&#39;AI");
    expect(decisionRecordHtml(input(), t, "it")).not.toContain("Testo per il cliente");
  });

  it("escapes what comes from the client's files", () => {
    const html = decisionRecordHtml(input(), t, "it");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("refuses to compare runs on different models and adds the sensitivity table", () => {
    const html = decisionRecordHtml(input({
      deltas: { kpis: { cycle: null, waiting: null, costPerCase: null, throughput: null }, paired: null, mismatch: true },
      tornado: { center: 3600, delta: 0.2, total: 3, completed: 3, failed: 0, rows: [
        { key: "arrival:", kind: "arrival", label: "Tempo fra due arrivi", low: 6000, high: 3000, swing: 3000, negligible: false },
      ] },
    }), t, "it");
    expect(html).toContain("versioni diverse dell&#39;AS-IS");
    expect(html).not.toContain("Una sola simulazione per scenario");
    expect(html).toContain("Tempo fra due arrivi");
    expect(html).toContain("Quanti casi arrivano davvero");
  });
});
