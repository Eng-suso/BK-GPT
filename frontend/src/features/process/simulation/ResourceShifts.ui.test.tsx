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
const MORNINGS = { id: "cal-1", name: "Mattine", periods: [{ from_day: "MONDAY" as const, to_day: "FRIDAY" as const, begin: "09:00", end: "12:00" }] };
const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
  calendars: [MORNINGS],
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

describe("turni di rinforzo (SIM-30)", () => {
  it("aggiunge due unità la mattina e le manda con la risorsa", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);
    const block = document.querySelector('[data-resource-shifts="r1"]') as HTMLElement;

    await user.click(within(block).getByRole("button", { name: "Aggiungi un turno a Ufficio" }));
    const amount = within(block).getByLabelText("Unità in più · Ufficio · turno 2");
    await user.clear(amount);
    await user.type(amount, "2");

    expect(scenarioToInput(current(), null).resources?.[0].shifts).toEqual([{ amount: 2, calendarId: "cal-1" }]);
  });

  it("senza calendari spiega come crearne uno, e un turno senza calendario blocca il run", () => {
    render(<Harness initial={{ ...READY, calendars: [] }} />);
    expect(screen.getByText(/crea prima il suo calendario/)).toBeInTheDocument();
    const orphan = { ...READY, calendars: [], resources: [{ ...READY.resources[0], shifts: [{ amount: 1, calendarId: "cal-1" }] }] };
    expect(scenarioParameterIssues(orphan).shifts).toBe(1);
  });
});
