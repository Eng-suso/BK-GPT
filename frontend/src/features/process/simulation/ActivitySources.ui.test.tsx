import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { DEFAULT_SCENARIO, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationClaims } from "./simulationTypes";

const TEMPLATE = {
  resources: [],
  standard_calendar: { id: "std", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  tasks: [{ element_id: "T_approve", name: "Approva", type: "userTask" }, { element_id: "T_pay", name: "Paga", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const CLAIMS: SimulationClaims = {
  sources: 1,
  activities: [
    { element_id: "T_approve", name: "Approva", proposals: [
      { claim_id: 7, statement: "Il responsabile approva ogni ordine.", quote: "approva ogni ordine", quote_verified: true,
        source_id: "s1", source_name: "procedura.pdf", score: 1, duration_hint: { text: "30 minuti", seconds: 1800 } },
      { claim_id: 8, statement: "Le approvazioni urgenti passano dal CFO.", quote: "approvazioni urgenti", quote_verified: true,
        source_id: "s1", source_name: "procedura.pdf", score: 1, duration_hint: null },
    ] },
    { element_id: "T_pay", name: "Paga", proposals: [] },
  ],
};

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: {
    T_approve: { meanMinutes: 20, distribution: "norm", resourceId: "r1" },
    T_pay: { meanMinutes: 10, distribution: "norm", resourceId: "r1" },
  },
};

function Harness() {
  const [draft, setDraft] = React.useState(READY);
  return (
    <>
      <SimulationConfigRail template={TEMPLATE} templateLoading={false} claims={CLAIMS} draft={draft} onDraftChange={setDraft}
        isRunning={false} error={null} onRun={() => undefined} focusElementId={null} />
      <output data-testid="draft">{JSON.stringify(draft)}</output>
    </>
  );
}

const current = (): ScenarioDraft => JSON.parse(screen.getByTestId("draft").textContent ?? "{}");
const row = (name: string) => screen.getByText(name, { selector: "p" }).closest("li") as HTMLElement;

describe("client sources of an activity in the scenario panel (SIM-07)", () => {
  it("proposes the statements, links one and sends it with the task", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const approve = row("Approva");
    expect(within(approve).getByText("Il responsabile approva ogni ordine.")).toBeInTheDocument();
    expect(within(approve).getByText("La fonte indica 30 min («30 minuti»): è un riferimento, non il valore.")).toBeInTheDocument();
    // Nessuna proposta, nessun blocco: l'attività senza fonti resta pulita.
    expect(within(row("Paga")).queryByText("Fonti del cliente")).not.toBeInTheDocument();

    await user.click(within(approve).getByRole("button", { name: "Collega come fonte per Approva: Il responsabile approva ogni ordine." }));
    expect(within(approve).getByText("Fonte collegata · procedura.pdf")).toBeInTheDocument();
    const [task] = (scenarioToInput(current(), null).tasks ?? []).filter((t) => t.elementId === "T_approve");
    expect(task.claims).toEqual([{ claimId: 7, label: "procedura.pdf" }]);
    // La durata resta quella del pannello.
    expect(task.meanSeconds).toBe(1200);
  });

  it("hides a dismissed proposal and unlinks a linked one", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const approve = row("Approva");

    await user.click(within(approve).getByRole("button", { name: "Non pertinente per Approva: Le approvazioni urgenti passano dal CFO." }));
    expect(within(approve).queryByText("Le approvazioni urgenti passano dal CFO.")).not.toBeInTheDocument();
    expect(current().dismissedClaims).toEqual({ T_approve: [8] });

    await user.click(within(approve).getByRole("button", { name: "Collega come fonte per Approva: Il responsabile approva ogni ordine." }));
    await user.click(within(approve).getByRole("button", { name: "Scollega da Approva: Il responsabile approva ogni ordine." }));
    expect(current().tasks.T_approve.claims).toEqual([]);
  });
});
