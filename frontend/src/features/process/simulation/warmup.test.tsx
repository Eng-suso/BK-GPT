import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { WarmupNote } from "./CostBreakdown";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, warmupIssue, type ScenarioDraft } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

const draft = (patch: Partial<ScenarioDraft> = {}): ScenarioDraft => ({ ...structuredClone(DEFAULT_SCENARIO), totalCases: 100, ...patch });

describe("warm-up cases (SIM-03)", () => {
  it("sends the warm-up only when set", () => {
    expect(scenarioToInput(draft({ warmupCases: 20 }), null).warmupCases).toBe(20);
    expect(scenarioToInput(draft(), null)).not.toHaveProperty("warmupCases");
  });

  it("needs a whole number that leaves cases to measure", () => {
    expect(warmupIssue(draft({ warmupCases: 2.5 }))).toBe("notWhole");
    expect(warmupIssue(draft({ warmupCases: 100 }))).toBe("noCaseLeft");
    expect(warmupIssue(draft({ warmupCases: 99 }))).toBeNull();
    expect(scenarioParameterIssues(draft({ warmupCases: 100 }))).toMatchObject({ warmup: true, ready: false });
  });

  it("tells which cases the results are computed on", () => {
    const run = { summary: { warmup: { excludedCases: 20, measuredCases: 80 } } } as unknown as SimulationRun;
    render(<WarmupNote run={run} />);
    expect(screen.getByText("Risultati calcolati su 80 casi: i primi 20 servivano a riempire le code e sono esclusi.")).toBeInTheDocument();
  });
});
