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
  tasks: [{ element_id: "T0", name: "Verifica", type: "userTask" }, { element_id: "T1", name: "Approva", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: {
    T0: { meanMinutes: 5, distribution: "norm", resourceId: "r1" },
    T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" },
  },
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
const block = (id: string) => document.querySelector(`[data-outcome="${id}"]`) as HTMLElement;

describe("esito dell'attività nel pannello (SIM-31b)", () => {
  it("accende l'esito, lo manda con l'attività e lo offre alle regole delle attività dopo", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    await user.click(within(block("T0")).getByRole("checkbox", { name: "Dà un esito · Verifica" }));
    const name = within(block("T0")).getByRole("textbox", { name: "Nome dell'esito · Verifica" });
    await user.clear(name);
    await user.type(name, "verifica");

    expect(scenarioToInput(current(), null).tasks?.find((t) => t.elementId === "T0")?.outcome).toEqual({
      attribute: "verifica", options: [{ value: "OK", probability: 0.8 }, { value: "KO", probability: 0.2 }],
    });
    // Senza attributi del caso, la rilavorazione di Approva può ora usare una regola: l'esito.
    const flow = document.querySelector('[data-flow-rules="T1"]') as HTMLElement;
    await user.click(within(flow).getByRole("checkbox", { name: "Alcuni casi la rifanno · Approva" }));
    expect(within(flow).getByRole("button", { name: "Solo per alcuni casi" })).toBeInTheDocument();
  });

  it("spiega un nome già preso e lo segna sul campo", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, tasks: { ...READY.tasks, T1: { ...READY.tasks.T1!, outcome: { name: "esito", categories: [{ value: "OK", percent: 100 }] } } } }} />);

    await user.click(within(block("T0")).getByRole("checkbox", { name: "Dà un esito · Verifica" }));
    // Il nome proposto è già diverso dagli altri: lo si rende uguale a mano.
    expect(within(block("T0")).getByRole("textbox", { name: "Nome dell'esito · Verifica" })).toHaveValue("esito Verifica");
    await user.clear(within(block("T0")).getByRole("textbox", { name: "Nome dell'esito · Verifica" }));
    await user.type(within(block("T0")).getByRole("textbox", { name: "Nome dell'esito · Verifica" }), "esito");

    expect(within(block("T0")).getByRole("alert")).toHaveTextContent("Questo nome è già di un attributo del caso o di un altro esito.");
    expect(within(block("T0")).getByRole("textbox", { name: "Nome dell'esito · Verifica" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Esiti da completare: 2/)).toBeInTheDocument();
  });
});
