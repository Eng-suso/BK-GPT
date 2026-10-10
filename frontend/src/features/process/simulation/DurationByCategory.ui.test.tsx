import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE = {
  resources: [],
  standard_calendar: { id: "std", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  tasks: [{ element_id: "T1", name: "Approva", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const TYPE = { id: "attr-1", name: "tipo", kind: "category" as const, categories: [{ value: "premium", percent: 30 }, { value: "standard", percent: 70 }] };
const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
  caseAttributes: [TYPE],
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

describe("durations by case category (SIM-32)", () => {
  it("gives premium cases their own duration and sends one per category", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);
    const block = document.querySelector('[data-duration-by="T1"]') as HTMLElement;

    await user.selectOptions(within(block).getByLabelText("La durata cambia con · Approva"), "attr-1");
    expect(within(block).getByText("Casi con tipo = premium")).toBeInTheDocument();
    const premium = within(block).getByLabelText("Durata, min · Approva · premium");
    await user.clear(premium);
    await user.type(premium, "10");

    const [task] = scenarioToInput(current(), null).tasks ?? [];
    expect(task.durationBy?.attribute).toBe("tipo");
    expect(task.durationBy?.variants.map((v) => [v.value, v.meanSeconds])).toEqual([["premium", 600], ["standard", 1200]]);
    // L'attributo usato da una durata non si toglie.
    expect(screen.getByRole("button", { name: /Togli l'attributo tipo/ })).toBeDisabled();
  });

  it("blocks the run when the attribute of a duration is gone", () => {
    const orphan = { ...READY, caseAttributes: [], tasks: { T1: { ...READY.tasks.T1, durationBy: { attributeId: "attr-1", variants: {} } } } };
    expect(scenarioParameterIssues(orphan)).toMatchObject({ durations: 1, ready: false });
    render(<Harness initial={orphan} />);
    expect(screen.getByRole("alert")).toHaveTextContent("L'attributo scelto non c'è più o non è a categorie");
  });

  it("hides the choice when no attribute has categories", () => {
    render(<Harness initial={{ ...READY, caseAttributes: [] }} />);
    expect(document.querySelector('[data-duration-by="T1"]')).toBeNull();
  });
});
