import { describe, expect, it } from "vitest";

import { buildInputConfidence } from "./simulationProvenance";
import { DEFAULT_SCENARIO, seedDraftFromTemplate, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioProvenance, ScenarioTemplate } from "./simulationTypes";

const TEMPLATE: ScenarioTemplate = {
  tasks: [
    { element_id: "Task_Review", name: "Verifica", type: "task" },
    { element_id: "Task_Approve", name: "Approva", type: "task" },
  ],
  gateways: [
    {
      element_id: "Decision_1",
      name: "Completa?",
      type: "exclusiveGateway",
      branches: [
        { flow_id: "f1", flow_name: "Si", target_name: "Approva" },
        { flow_id: "f2", flow_name: "No", target_name: "Verifica" },
      ],
    },
  ],
};

function provenance(over: Partial<ScenarioProvenance> = {}): ScenarioProvenance {
  return {
    has_discovery: true,
    process_confidence: "medium",
    readiness_score: 70,
    missing_information: [],
    weak_points: [],
    elements: [
      {
        element_id: "Task_Review",
        kind: "activity",
        name: "Verifica",
        parameter: "duration",
        origin: "interview",
        confidence: "high",
        evidence: ["Un operatore controlla gli allegati."],
        open_questions: 0,
        hint_ref: { field: "steps", id: "s1", label: "Verifica" },
      },
      {
        element_id: "Task_Approve",
        kind: "activity",
        name: "Approva",
        parameter: "duration",
        origin: "ai_inferred",
        confidence: "low",
        evidence: [],
        open_questions: 0,
        hint_ref: null,
      },
      {
        element_id: "Decision_1",
        kind: "gateway",
        name: "Completa?",
        parameter: "branching",
        origin: "interview",
        confidence: "medium",
        evidence: [],
        open_questions: 1,
        hint_ref: { field: "decisions", id: "d1", label: "Completa?" },
      },
    ],
    ...over,
  };
}

function seeded(): ScenarioDraft {
  return seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
}

describe("buildInputConfidence", () => {
  it("returns all-low with no provenance", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, null);
    expect(ic.hasDiscovery).toBe(false);
    expect(ic.readiness.overall).toBe("low");
    expect(ic.activities.Task_Review.confidence).toBe("low");
  });

  it("a discovered activity left at default reads as estimated/medium", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    expect(ic.activities.Task_Review.source).toBe("estimated");
    expect(ic.activities.Task_Review.confidence).toBe("medium");
    expect(ic.activities.Task_Review.evidence).toHaveLength(1);
  });

  it("a discovered activity with a consultant-set duration reads as confirmed/high", () => {
    const draft = seeded();
    draft.tasks.Task_Review = { ...draft.tasks.Task_Review, meanMinutes: 42 };
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.activities.Task_Review.source).toBe("confirmed");
    expect(ic.activities.Task_Review.confidence).toBe("high");
  });

  it("an inferred activity at default is the weakest signal", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    expect(ic.activities.Task_Approve.source).toBe("default");
    expect(ic.activities.Task_Approve.confidence).toBe("low");
    expect(ic.readiness.lowConfidenceElementIds).toContain("Task_Approve");
  });

  it("an untouched even gateway keeps the backend confidence and flags open questions", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    expect(ic.gateways.Decision_1.source).toBe("inferred");
    expect(ic.gateways.Decision_1.confidence).toBe("medium");
    expect(ic.gateways.Decision_1.note).toBe("1");
  });

  it("editing the split off the even baseline marks the gateway confirmed", () => {
    const draft = seeded();
    draft.gateways.Decision_1 = { f1: 80, f2: 20 };
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.gateways.Decision_1.source).toBe("confirmed");
  });

  it("globals flip to confirmed once moved off the DEFAULT_SCENARIO value", () => {
    const draft = seeded();
    draft.totalCases = 500;
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.globals.cases.source).toBe("confirmed");
    expect(ic.globals.arrival.source).toBe("default");
  });

  it("rolls structure up from the backend origin ratio", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    const structure = ic.readiness.rows.find((r) => r.key === "structure")!;
    // 2 of 3 elements are interview-backed
    expect(structure.pct).toBeGreaterThan(50);
    expect(structure.pct).toBeLessThan(90);
  });

  it("a fully discovered + consultant-confirmed scenario reaches high overall", () => {
    const draft = seeded();
    draft.tasks.Task_Review = { ...draft.tasks.Task_Review, meanMinutes: 20 };
    draft.tasks.Task_Approve = { ...draft.tasks.Task_Approve, meanMinutes: 10 };
    draft.gateways.Decision_1 = { f1: 70, f2: 30 };
    draft.totalCases = 400;
    draft.arrivalIntervalMinutes = 12;
    draft.resources = [{ id: "res-1", name: "Team", costPerHour: 40, amount: 3 }];
    const strong = provenance({
      elements: provenance().elements.map((e) => ({
        ...e,
        origin: "interview" as const,
        confidence: "high" as const,
      })),
    });
    const ic = buildInputConfidence(draft, TEMPLATE, strong);
    expect(ic.readiness.overall).toBe("high");
  });
});
