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

function declared(id: string, confidence: "high" | "medium" | "low") {
  return {
    origin: "declared" as const,
    confidence,
    sources: [{ kind: "interview" as const, id }],
  };
}

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
        provenance: declared("steps:s1", "high"),
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
        provenance: { origin: "estimated", confidence: "low", sources: [] },
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
        provenance: declared("decisions:d1", "medium"),
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
    expect(ic.activities.Task_Review.origin).toBe("estimated");
    expect(ic.activities.Task_Review.confidence).toBe("medium");
    expect(ic.activities.Task_Review.evidence).toHaveLength(1);
    expect(ic.activities.Task_Review.sources).toEqual([{ kind: "interview", id: "steps:s1" }]);
  });

  it("a discovered activity with a consultant-set duration reads as manual/high", () => {
    const draft = seeded();
    draft.tasks.Task_Review = { ...draft.tasks.Task_Review, meanMinutes: 42 };
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.activities.Task_Review.origin).toBe("manual");
    expect(ic.activities.Task_Review.confidence).toBe("high");
  });

  it("an inferred activity at default is the weakest signal", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    expect(ic.activities.Task_Approve.origin).toBe("default");
    expect(ic.activities.Task_Approve.confidence).toBe("low");
    expect(ic.readiness.lowConfidenceElementIds).toContain("Task_Approve");
  });

  it("an untouched even gateway keeps the backend confidence and flags open questions", () => {
    const ic = buildInputConfidence(seeded(), TEMPLATE, provenance());
    expect(ic.gateways.Decision_1.origin).toBe("declared");
    expect(ic.gateways.Decision_1.confidence).toBe("medium");
    expect(ic.gateways.Decision_1.note).toBe("1");
  });

  it("editing the split off the even baseline marks the gateway manual", () => {
    const draft = seeded();
    draft.gateways.Decision_1 = { f1: 80, f2: 20 };
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.gateways.Decision_1.origin).toBe("manual");
  });

  it("globals flip to manual once moved off the DEFAULT_SCENARIO value", () => {
    const draft = seeded();
    draft.totalCases = 500;
    const ic = buildInputConfidence(draft, TEMPLATE, provenance());
    expect(ic.globals.cases.origin).toBe("manual");
    expect(ic.globals.arrival.origin).toBe("default");
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
    draft.resources = [{ id: "res-1", name: "Team", costPerHour: 40, amount: 3, parametersConfirmed: true }];
    draft.tasks = Object.fromEntries(Object.entries(draft.tasks).map(([id, task]) => [id, { ...task, resourceId: "res-1" }]));
    const strong = provenance({
      elements: provenance().elements.map((e) => ({
        ...e,
        provenance: declared(`steps:${e.element_id}`, "high"),
        confidence: "high" as const,
      })),
    });
    const ic = buildInputConfidence(draft, TEMPLATE, strong);
    expect(ic.readiness.overall).toBe("high");
  });
  it("adding a role alone does not confirm its parameters or incomplete assignments", () => {
    const draft = seeded();
    draft.resources = [{ id: "manual", name: "Team", costPerHour: 0, amount: 1, parametersConfirmed: false }];
    expect(buildInputConfidence(draft, TEMPLATE, null).resources.confidence).toBe("low");
    draft.resources[0].parametersConfirmed = true;
    expect(buildInputConfidence(draft, TEMPLATE, null).resources.confidence).toBe("low");
    draft.tasks = Object.fromEntries(Object.entries(draft.tasks).map(([id, task]) => [id, { ...task, resourceId: "manual" }]));
    expect(buildInputConfidence(draft, TEMPLATE, null).resources).toMatchObject({ origin: "manual", confidence: "high" });
  });

  it("an activity measured on an event log keeps the observed origin", () => {
    const observed = provenance({
      elements: provenance().elements.map((e) =>
        e.element_id === "Task_Approve"
          ? {
              ...e,
              provenance: {
                origin: "observed" as const,
                confidence: "high" as const,
                sources: [{ kind: "event_log" as const, id: "log-1" }],
              },
              confidence: "high" as const,
            }
          : e,
      ),
    });
    const ic = buildInputConfidence(seeded(), TEMPLATE, observed);
    expect(ic.activities.Task_Approve).toMatchObject({ origin: "observed", confidence: "high" });
    expect(ic.activities.Task_Approve.sources?.[0].kind).toBe("event_log");
  });
});
