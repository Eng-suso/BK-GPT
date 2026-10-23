import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { buildInputConfidence } from "./simulationProvenance";
import { DEFAULT_SCENARIO, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE = {
  resources: [],
  standard_calendar: { id: "std", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  tasks: [{ element_id: "T0", name: "Registra", type: "serviceTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Sistema ERP", costPerHour: 0, amount: 5, parametersConfirmed: true,
    shifts: [{ amount: 1, calendarId: "c1" }] }],
  calendars: [{ id: "c1", name: "Mattine", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "12:00" }] }],
  tasks: { T0: { meanMinutes: 1, distribution: "norm", resourceId: "r1" } },
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

describe("sistemi e macchine come risorse (SIM-09b)", () => {
  it("fa di una risorsa un sistema: niente turni, esecuzioni contemporanee, sempre disponibile", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);
    const card = document.querySelector('[data-resource-id="r1"]') as HTMLElement;

    await user.click(within(card).getByRole("button", { name: "Sistema" }));

    expect(within(card).getByRole("button", { name: "Sistema" })).toHaveAttribute("aria-pressed", "true");
    expect(within(card).getByText("Esecuzioni contemporanee")).toBeInTheDocument();
    expect(within(card).getByRole("combobox", { name: "Calendario di lavoro · Sistema ERP" })).toHaveDisplayValue("Sempre, 24 ore su 24");
    const resource = scenarioToInput(current(), null).resources?.[0];
    expect(resource).toMatchObject({ kind: "system" });
    expect(resource).not.toHaveProperty("shifts");
    expect(resource?.calendarId).toBeUndefined();
  });

  it("torna persona e la richiesta non porta più il tipo", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, resources: [{ ...READY.resources[0]!, kind: "system", shifts: undefined }] }} />);
    const card = document.querySelector('[data-resource-id="r1"]') as HTMLElement;

    await user.click(within(card).getByRole("button", { name: "Persone" }));

    expect(scenarioToInput(current(), null).resources?.[0]).not.toHaveProperty("kind");
  });

  it("un sistema senza calendario non abbassa la prontezza dei calendari", () => {
    const person = buildInputConfidence({ ...READY, resources: [{ ...READY.resources[0]!, shifts: undefined }] }, TEMPLATE, null);
    const system = buildInputConfidence({ ...READY, resources: [{ ...READY.resources[0]!, shifts: undefined, kind: "system" }] }, TEMPLATE, null);
    const calendars = (r: typeof person) => r.readiness.rows.find((row) => row.key === "calendars")?.pct ?? 0;
    expect(calendars(system)).toBeGreaterThan(calendars(person));
  });
});
