import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { CostBreakdown } from "./CostBreakdown";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

const draft = (patch: Partial<ScenarioDraft> = {}): ScenarioDraft => ({
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 1, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 10, distribution: "norm", resourceId: "r1", fixedCost: 12.5 }, T2: { meanMinutes: 10, distribution: "norm", resourceId: "r1" } },
  ...patch,
});

describe("fixed costs (SIM-10)", () => {
  it("sends the fixed cost of each activity and per case, only when set", () => {
    const input = scenarioToInput(draft({ caseFixedCost: 4 }), null);
    expect(input.caseFixedCost).toBe(4);
    expect(input.tasks?.find((t) => t.elementId === "T1")?.fixedCost).toBe(12.5);
    expect(input.tasks?.find((t) => t.elementId === "T2")).not.toHaveProperty("fixedCost");
    expect(scenarioToInput(draft(), null)).not.toHaveProperty("caseFixedCost");
  });

  it("blocks the run on a negative cost", () => {
    expect(scenarioParameterIssues(draft({ caseFixedCost: -1 }))).toMatchObject({ costs: true, ready: false });
    expect(scenarioParameterIssues(draft())).toMatchObject({ costs: false });
  });

  it("shows where the run cost comes from", () => {
    const run = { summary: { cost: { total: 630, perCase: 63, breakdown: { resources: 500, activities: 100, cases: 30 } } } } as unknown as SimulationRun;
    render(<CostBreakdown run={run} />);
    const section = screen.getByRole("region", { name: "Costo dello scenario" });
    expect(section).toHaveTextContent("Tempo delle risorse: 500");
    expect(section).toHaveTextContent("Costi fissi delle attività: 100");
    expect(section).toHaveTextContent("Costi fissi per caso: 30");
  });

  it("stays silent without fixed costs", () => {
    const run = { summary: { cost: { total: 500, perCase: 50 } } } as unknown as SimulationRun;
    const { container } = render(<CostBreakdown run={run} />);
    expect(container).toBeEmptyDOMElement();
  });
});
