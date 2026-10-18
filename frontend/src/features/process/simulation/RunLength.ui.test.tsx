import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { HorizonNote } from "./CostBreakdown";
import { RunLength } from "./RunLength";
import {
  DEFAULT_SCENARIO,
  parseScenarioDraft,
  scenarioParameterIssues,
  scenarioToInput,
  warmupIssue,
  type ScenarioDraft,
} from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

function Harness() {
  const [draft, setDraft] = React.useState<ScenarioDraft>(structuredClone(DEFAULT_SCENARIO));
  return (
    <>
      <RunLength draft={draft} onChange={(fields) => setDraft({ ...draft, ...fields })} />
      <output data-testid="draft">{JSON.stringify({ totalCases: draft.totalCases, horizonDays: draft.horizonDays ?? null })}</output>
    </>
  );
}

const current = () => JSON.parse(screen.getByTestId("draft").textContent ?? "{}");

describe("simulated period (SIM-03)", () => {
  it("switches between a number of cases and a period in days", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByLabelText("Casi")).toHaveValue(100);

    await user.selectOptions(screen.getByLabelText("Simula per"), "period");
    expect(current()).toEqual({ totalCases: 100, horizonDays: 20 });
    expect(screen.getByText(/per 20 giorni; a fine periodo quelli non finiti restano aperti/)).toBeInTheDocument();

    const days = screen.getByLabelText("Giorni simulati");
    await user.clear(days);
    await user.type(days, "400");
    expect(screen.getByRole("alert")).toHaveTextContent("Il periodo va da 1 a 366 giorni interi.");

    await user.selectOptions(screen.getByLabelText("Simula per"), "cases");
    expect(current()).toEqual({ totalCases: 100, horizonDays: null });
  });

  it("sends the period, blocks an invalid one and keeps it in the saved draft", () => {
    const draft = { ...structuredClone(DEFAULT_SCENARIO), horizonDays: 28, warmupCases: 500 };
    expect(scenarioToInput(draft, null).horizonDays).toBe(28);
    // Con un periodo i casi li stima il servizio: il riscaldamento non si confronta con totalCases.
    expect(warmupIssue(draft)).toBeNull();
    expect(scenarioParameterIssues(draft).ready).toBe(true);
    expect(scenarioParameterIssues({ ...draft, horizonDays: 1.5 }).horizon).toBe(true);
    expect(scenarioToInput(structuredClone(DEFAULT_SCENARIO), null).horizonDays).toBeUndefined();
    expect(parseScenarioDraft({ horizonDays: 28 }).horizonDays).toBe(28);
    expect(parseScenarioDraft({ horizonDays: "28" }).horizonDays).toBeUndefined();
  });

  it("tells how many cases the period completed and left open", () => {
    const run = { summary: { horizon: { days: 20, arrivedCases: 330, completedCases: 318, openCases: 12, covered: true } } } as unknown as SimulationRun;
    const { rerender } = render(<HorizonNote run={run} />);
    expect(screen.getByText("Periodo di 20 giorni: 318 casi completati su 330 arrivati, 12 ancora aperti a fine periodo. I risultati misurano i completati.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    const uncovered = { summary: { horizon: { ...run.summary!.horizon!, covered: false } } } as unknown as SimulationRun;
    rerender(<HorizonNote run={uncovered} />);
    expect(screen.getByRole("status")).toHaveTextContent("non coprono tutto il periodo");
  });
});
