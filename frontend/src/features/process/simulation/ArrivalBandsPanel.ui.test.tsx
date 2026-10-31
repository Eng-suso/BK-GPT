import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { DEFAULT_SCENARIO, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE = {
  resources: [],
  standard_calendar: { id: "std", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  tasks: [{ element_id: "T1", name: "Approva", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;
const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
};

function Harness() {
  const [draft, setDraft] = React.useState(READY);
  return (
    <>
      <SimulationConfigRail template={TEMPLATE} templateLoading={false} draft={draft} onDraftChange={setDraft}
        isRunning={false} error={null} onRun={() => undefined} focusElementId={null} />
      <output data-testid="draft">{JSON.stringify(draft)}</output>
    </>
  );
}

const current = (): ScenarioDraft => JSON.parse(screen.getByTestId("draft").textContent ?? "{}");

describe("fasce degli arrivi nel pannello (SIM-08)", () => {
  it("aggiunge un picco del mattino e un pomeriggio calmo, e li manda", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const block = document.querySelector("[data-arrival-bands]") as HTMLElement;

    await user.click(within(block).getByRole("checkbox", { name: "Ritmo diverso per fascia oraria" }));
    // Con le fasce distribuzione e calendario degli arrivi spariscono: non conterebbero.
    expect(screen.queryByText("Calendario degli arrivi")).not.toBeInTheDocument();
    await user.click(within(block).getByRole("button", { name: "Aggiungi una fascia" }));
    const quiet = within(block).getByLabelText("Un caso ogni, min · Fascia 2");
    await user.clear(quiet);
    await user.type(quiet, "45");

    expect(scenarioToInput(current(), null).arrival?.bands).toEqual([
      { fromDay: "MONDAY", toDay: "FRIDAY", begin: "09:00", end: "12:00", meanSeconds: 300 },
      { fromDay: "MONDAY", toDay: "FRIDAY", begin: "14:00", end: "17:00", meanSeconds: 2700 },
    ]);
  });

  it("segnala sul campo una fascia che si sovrappone e blocca il run", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const block = document.querySelector("[data-arrival-bands]") as HTMLElement;
    await user.click(within(block).getByRole("checkbox", { name: "Ritmo diverso per fascia oraria" }));
    await user.click(within(block).getByRole("button", { name: "Aggiungi una fascia" }));
    const begin = within(block).getByLabelText("Ora di inizio · Fascia 2");
    await user.clear(begin);
    await user.type(begin, "10:00");

    expect(within(block).getByRole("alert")).toHaveTextContent("Si sovrappone a una fascia precedente.");
    expect(begin).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();

    await user.click(within(block).getByRole("button", { name: "Togli Fascia 2" }));
    expect(within(block).queryByRole("alert")).not.toBeInTheDocument();
  });
});
