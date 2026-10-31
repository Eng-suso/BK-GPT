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
  tasks: [{ element_id: "T0", name: "Ricevi", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T0: { meanMinutes: 5, distribution: "norm", resourceId: "r1" } },
};

function Harness({ initial }: { initial: ScenarioDraft }) {
  const [draft, setDraft] = React.useState(initial);
  return (
    <>
      <SimulationConfigRail template={TEMPLATE} templateLoading={false} draft={draft} onDraftChange={setDraft}
        isRunning={false} error={null} onRun={() => undefined} focusElementId={null} />
      <output data-testid="draft">{JSON.stringify(draft)}</output>
    </>
  );
}

const current = (): ScenarioDraft => JSON.parse(screen.getByTestId("draft").textContent ?? "{}");
const block = () => document.querySelector("[data-arrival-months]") as HTMLElement;

describe("ritmo per mese nel pannello (SIM-08b)", () => {
  it("aggiunge dicembre e agosto con la loro variazione", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    await user.click(within(block()).getByRole("checkbox", { name: "Ritmo diverso per mese" }));
    const december = within(block()).getByLabelText("Variazione degli arrivi a dicembre, %");
    await user.clear(december);
    await user.type(december, "40");
    await user.click(within(block()).getByRole("button", { name: "Aggiungi un mese" }));
    await user.selectOptions(within(block()).getByRole("combobox", { name: "Mese 2" }), "8");
    const august = within(block()).getByLabelText("Variazione degli arrivi a agosto, %");
    await user.clear(august);
    await user.type(august, "-50");

    expect(scenarioToInput(current(), null).arrival?.months).toEqual([{ month: 12, factor: 1.4 }, { month: 8, factor: 0.5 }]);
  });

  it("con arrivi non esponenziali e senza fasce spiega perché non parte", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, arrival: { distribution: "norm" } }} />);

    await user.click(within(block()).getByRole("checkbox", { name: "Ritmo diverso per mese" }));

    expect(within(block()).getByRole("alert")).toHaveTextContent("vale con le fasce orarie o con arrivi esponenziali");
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();
  });
});
