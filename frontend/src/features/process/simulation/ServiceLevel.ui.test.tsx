import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ServiceLevelFields, ServiceLevelOutcome } from "./ServiceLevel";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type SlaDraft } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

function Harness() {
  const [sla, setSla] = React.useState<SlaDraft | undefined>(undefined);
  return (
    <>
      <ServiceLevelFields sla={sla} onChange={setSla} />
      <output data-testid="sla">{JSON.stringify(sla ?? null)}</output>
    </>
  );
}

const current = (): SlaDraft | null => JSON.parse(screen.getByTestId("sla").textContent ?? "null");

describe("service objective (SIM-13)", () => {
  it("adds an objective, reads it as a sentence and sends it in seconds", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Aggiungi un obiettivo di servizio" }));
    expect(screen.getByText("Almeno il 90% dei casi deve chiudersi entro 2 giorni.")).toBeInTheDocument();

    const share = screen.getByLabelText("Per almeno il % dei casi");
    await user.clear(share);
    await user.type(share, "0");
    expect(screen.getByRole("alert")).toHaveTextContent("La quota va da 1 a 100.");

    await user.clear(share);
    await user.type(share, "80");
    const sla = current()!;
    const draft = { ...structuredClone(DEFAULT_SCENARIO), sla };
    expect(scenarioToInput(draft, null).sla).toEqual({ targetSeconds: 2 * 86_400, share: 0.8 });
    expect(scenarioParameterIssues(draft).sla).toBe(false);

    await user.click(screen.getByRole("button", { name: "Togli l'obiettivo" }));
    expect(current()).toBeNull();
  });

  it("tells whether the run met the objective", () => {
    const run = { summary: { sla: { target_seconds: 172_800, share_target: 0.9, share_within: 0.87, cases: 100, late_cases: 13, met: false } } } as unknown as SimulationRun;
    render(<ServiceLevelOutcome run={run} />);
    const outcome = screen.getByRole("region", { name: "Obiettivo di servizio" });
    expect(within(outcome).getByText("Non rispettato")).toBeInTheDocument();
    expect(outcome).toHaveTextContent("87% dei casi chiusi entro 2g (obiettivo 90%).");
    expect(outcome).toHaveTextContent("13 casi su 100 oltre il tempo.");
  });
});
