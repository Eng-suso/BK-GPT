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
  tasks: [{ element_id: "T0", name: "Ricevi", type: "userTask" }, { element_id: "T1", name: "Approva", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const AMOUNT = { id: "attr-1", name: "importo", kind: "number" as const, minimum: 100, maximum: 12000 };
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
const approve = () => scenarioToInput(current(), null).tasks?.find((t) => t.elementId === "T1");
const block = () => document.querySelector('[data-flow-rules="T1"]') as HTMLElement;

describe("salto e rilavorazione nel pannello (SIM-35)", () => {
  it("fa saltare l'attività a una quota dei casi", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    await user.click(within(block()).getByRole("checkbox", { name: "Alcuni casi la saltano · Approva" }));
    const share = within(block()).getByLabelText("Casi che la saltano, % · Approva");
    await user.clear(share);
    await user.type(share, "35");

    expect(approve()?.skip).toEqual({ probability: 0.35 });
  });

  it("rimanda indietro una quota dei casi, con un tetto, e blocca una quota impossibile", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    await user.click(within(block()).getByRole("checkbox", { name: "Alcuni casi la rifanno · Approva" }));
    await user.selectOptions(within(block()).getByLabelText("Si riparte da · Approva"), "T0");
    const repeats = within(block()).getByLabelText("Al più, volte per caso · Approva");
    await user.clear(repeats);
    await user.type(repeats, "2");
    expect(approve()?.rework).toEqual({ backTo: "T0", probability: 0.1, maxRepeats: 2 });

    const share = within(block()).getByLabelText("Tornano indietro, % a ogni passaggio · Approva");
    await user.clear(share);
    await user.type(share, "100");
    expect(within(block()).getByRole("alert")).toHaveTextContent("fra 0 e 100, esclusi");
    expect(share).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Attività con salto o rilavorazione da correggere: 1")).toBeInTheDocument();
  });

  it("limita il salto ai casi di una regola, e l'attributo usato non si toglie", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, caseAttributes: [AMOUNT] }} />);

    await user.click(within(block()).getByRole("checkbox", { name: "Alcuni casi la saltano · Approva" }));
    await user.click(within(block()).getByRole("button", { name: "Solo per alcuni casi" }));
    await user.type(within(block()).getByLabelText("Valore per importo"), "1000");

    expect(approve()?.skip?.condition).toEqual({ any_of: [[{ attribute: "importo", operator: ">", value: 1000 }]] });
    expect(screen.getByRole("button", { name: /Togli l'attributo importo/ })).toBeDisabled();

    await user.click(within(block()).getByRole("button", { name: "Per tutti i casi" }));
    expect(approve()?.skip).toEqual({ probability: 0.2 });
  });
});
