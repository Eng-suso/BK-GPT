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

describe("fasce orarie della durata nel pannello (SIM-33b)", () => {
  it("rallenta il fine giornata del 30% e lo manda come fattore", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const block = document.querySelector('[data-duration-windows="T1"]') as HTMLElement;

    await user.click(within(block).getByRole("checkbox", { name: "La durata cambia con l'ora d'inizio · Approva" }));
    await user.click(within(block).getByRole("button", { name: "Aggiungi una fascia" }));
    const saturday = within(block).getByLabelText("Variazione della durata, % · Fascia oraria 2 · Approva");
    await user.clear(saturday);
    await user.type(saturday, "-20");

    expect(scenarioToInput(current(), null).tasks.find((t) => t.elementId === "T1")?.durationWindows).toEqual([
      { fromDay: "MONDAY", toDay: "FRIDAY", begin: "16:00", end: "18:00", factor: 1.3 },
      { fromDay: "SATURDAY", toDay: "SATURDAY", begin: "09:00", end: "13:00", factor: 0.8 },
    ]);
  });

  it("segnala una fascia che si sovrappone o una variazione fuori scala e blocca il run", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const block = document.querySelector('[data-duration-windows="T1"]') as HTMLElement;
    await user.click(within(block).getByRole("checkbox", { name: "La durata cambia con l'ora d'inizio · Approva" }));
    const percent = within(block).getByLabelText("Variazione della durata, % · Fascia oraria 1 · Approva");
    await user.clear(percent);
    await user.type(percent, "-100");

    expect(within(block).getByRole("alert")).toHaveTextContent("La variazione va da -99% a +900%.");
    expect(percent).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();

    await user.clear(percent);
    await user.type(percent, "10");
    await user.click(within(block).getByRole("button", { name: "Aggiungi una fascia" }));
    const from = within(block).getByLabelText("Dal giorno · Fascia oraria 2 · Approva");
    await user.selectOptions(from, "FRIDAY");
    const begin = within(block).getByLabelText("Ora di inizio · Fascia oraria 2 · Approva");
    await user.clear(begin);
    await user.type(begin, "17:00");
    // Il sabato finiva alle 13: prima l'ordine degli orari, poi la sovrapposizione col venerdi'.
    expect(within(block).getByRole("alert")).toHaveTextContent("L'ora di fine deve venire dopo quella di inizio");
    const end = within(block).getByLabelText("Ora di fine · Fascia oraria 2 · Approva");
    await user.clear(end);
    await user.type(end, "18:00");
    expect(within(block).getByRole("alert")).toHaveTextContent("Si sovrappone a una fascia precedente.");

    await user.click(within(block).getByRole("button", { name: "Togli Fascia oraria 2 · Approva" }));
    expect(within(block).queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeEnabled();
  });
});
