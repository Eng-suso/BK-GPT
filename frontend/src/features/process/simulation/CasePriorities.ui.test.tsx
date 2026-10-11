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
  tasks: [{ element_id: "T1", name: "Verifica", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
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
const section = () => screen.getByText(/Quando più casi aspettano la stessa risorsa/).closest("[data-sim-priorities]") as HTMLElement;

describe("case priorities in the scenario panel (SIM-12)", () => {
  it("needs a case attribute before a priority can be added", () => {
    render(<Harness initial={READY} />);
    expect(within(section()).getByRole("button", { name: "Aggiungi una priorità" })).toBeDisabled();
    expect(within(section()).getByText("Per dare una priorità, definisci prima un attributo del caso.")).toBeInTheDocument();
  });

  it("serves premium cases first and sends the priority with the run", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, caseAttributes: [{ id: "attr-1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 20 }, { value: "standard", percent: 80 }] }] }} />);

    await user.click(within(section()).getByRole("button", { name: "Aggiungi una priorità" }));
    const level = within(section()).getByRole("group", { name: "Priorità 1" });
    expect(level).toHaveTextContent("Passano prima i casi con tipo = premium.");
    expect(scenarioToInput(current(), null).modelPatch?.priority_rules).toEqual([
      { level: 1, condition: { any_of: [[{ attribute: "tipo", operator: "=", value: "premium" }]] } },
    ]);
    // L'attributo usato da una priorità non si toglie.
    expect(screen.getByRole("button", { name: /Togli l'attributo tipo/ })).toBeDisabled();

    await user.click(within(section()).getByRole("button", { name: "Togli la priorità 1" }));
    expect(current().casePriorities).toEqual([]);
  });
});
