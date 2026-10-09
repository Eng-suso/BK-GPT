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
  tasks: [{ element_id: "T_approve", name: "Approva", type: "userTask" }],
  gateways: [],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [
    { id: "clerk", name: "Impiegato", costPerHour: 30, amount: 2, parametersConfirmed: true },
    { id: "senior", name: "Senior", costPerHour: 60, amount: 1, parametersConfirmed: true },
  ],
  tasks: { T_approve: { meanMinutes: 20, distribution: "norm", resourceId: "clerk", assignmentSource: "manual" } },
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
const activity = () => screen.getByText("Approva", { selector: "p" }).closest("li") as HTMLElement;

describe("other roles of an activity in the scenario panel", () => {
  it("adds a second role with its own duration and sends both", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    await user.click(within(activity()).getByRole("button", { name: "Aggiungi un altro ruolo a Approva" }));
    const other = within(activity()).getByRole("listitem");
    expect(within(other).getByRole("combobox", { name: "Altro ruolo · Approva" })).toHaveTextContent("Senior");
    expect(within(activity()).getByText("Ogni caso va al primo ruolo libero. Ogni ruolo ha la sua durata.")).toBeInTheDocument();

    const duration = within(other).getByLabelText("Durata, min · Approva · Senior");
    await user.clear(duration);
    await user.type(duration, "8");

    const [task] = scenarioToInput(current(), null).tasks ?? [];
    expect(task.otherAssignments).toMatchObject([{ resourceId: "senior", meanSeconds: 480, distribution: "norm" }]);
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeEnabled();
    // Tutti i ruoli sono usati: niente terzo ruolo, e il pannello dice perché.
    expect(within(activity()).getByRole("button", { name: "Aggiungi un altro ruolo a Approva" })).toBeDisabled();
  });

  it("removes another role on request", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, tasks: { T_approve: { ...READY.tasks.T_approve, otherAssignments: [{ resourceId: "senior", meanMinutes: 10, distribution: "fixed" }] } } }} />);

    await user.click(within(activity()).getByRole("button", { name: "Togli Senior da Approva" }));
    expect(current().tasks.T_approve.otherAssignments).toEqual([]);
    expect(within(activity()).queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("drops the role from the activity when the resource is removed", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...READY, tasks: { T_approve: { ...READY.tasks.T_approve, otherAssignments: [{ resourceId: "senior", meanMinutes: 10, distribution: "fixed" }] } } }} />);

    await user.click(screen.getByRole("button", { name: "Rimuovi ruolo Senior" }));
    expect(current().tasks.T_approve.otherAssignments).toEqual([]);
    expect(within(activity()).getByText(/Tutti i ruoli svolgono già questa attività/)).toBeInTheDocument();
  });

  it("blocks the run while another role has a duration to fix", async () => {
    render(<Harness initial={{ ...READY, tasks: { T_approve: { ...READY.tasks.T_approve, otherAssignments: [{ resourceId: "senior", meanMinutes: 10, distribution: "uniform" }] } } }} />);

    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();
    expect(screen.getByText("Attività con durata da correggere: 1")).toBeInTheDocument();
    expect(within(activity()).getByRole("alert")).toBeInTheDocument();
  });
});
