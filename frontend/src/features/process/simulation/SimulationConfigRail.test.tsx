import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { DEFAULT_SCENARIO, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE: ScenarioTemplate = {
  resources: [],
  standard_calendar: {
    id: "delir-calendar-standard",
    name: "Standard office calendar",
    periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }],
  },
  tasks: [{ element_id: "T1", name: "Verifica", type: "userTask" }],
  gateways: [],
};

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
};

/** Il pannello con la bozza in stato: ogni modifica rientra come nuova bozza. */
function Harness({ initial, onRun }: { initial: ScenarioDraft; onRun?: () => void }) {
  const [draft, setDraft] = React.useState(initial);
  return (
    <>
      <SimulationConfigRail
        template={TEMPLATE}
        templateLoading={false}
        draft={draft}
        onDraftChange={setDraft}
        isRunning={false}
        error={null}
        onRun={onRun ?? (() => undefined)}
        focusElementId={null}
      />
      <output data-testid="draft">{JSON.stringify(draft)}</output>
    </>
  );
}

const current = (): ScenarioDraft => JSON.parse(screen.getByTestId("draft").textContent ?? "{}");

describe("SimulationConfigRail", () => {
  it("offers the six Prosimos distributions and nothing else", () => {
    render(<Harness initial={READY} />);
    const select = screen.getByLabelText("Distribuzione · Verifica");
    const options = within(select).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(options).toEqual(["fixed", "expon", "uniform", "norm", "lognorm", "gamma"]);
  });

  it("shows the parameters each distribution uses and states the defaults", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    expect(screen.getByLabelText("Dev. std, min · Verifica")).toHaveValue(null);
    expect(screen.getByText(/deviazione standard al 10% della media/)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Distribuzione · Verifica"), "fixed");
    expect(screen.queryByLabelText("Dev. std, min · Verifica")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Minimo, min · Verifica")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Distribuzione · Verifica"), "lognorm");
    await user.type(screen.getByLabelText("Dev. std, min · Verifica"), "5");
    expect(current().tasks.T1).toMatchObject({ distribution: "lognorm", stdMinutes: 5 });
  });

  it("blocks the run until a uniform has both bounds in order", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    render(<Harness initial={READY} onRun={onRun} />);

    await user.selectOptions(screen.getByLabelText("Distribuzione · Verifica"), "uniform");
    expect(screen.queryByLabelText("Durata, min · Verifica")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Indica minimo e massimo.");
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();
    expect(screen.getByText("Attività con durata da correggere: 1")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Minimo, min · Verifica"), "30");
    await user.type(screen.getByLabelText("Massimo, min · Verifica"), "10");
    expect(screen.getByRole("alert")).toHaveTextContent("Il minimo deve essere minore del massimo.");

    await user.clear(screen.getByLabelText("Massimo, min · Verifica"));
    await user.type(screen.getByLabelText("Massimo, min · Verifica"), "45");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Avvia simulazione" }));
    expect(onRun).toHaveBeenCalledOnce();
  });

  it("adds a calendar, assigns it to a resource and returns the resource to the standard one on removal", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    expect(screen.getByText("Lun–Ven 09:00–17:00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aggiungi calendario" }));
    const name = screen.getByLabelText("Nome del calendario");
    await user.clear(name);
    await user.type(name, "Turno sabato");
    const calendar = screen.getByLabelText("Nome del calendario").closest("li") as HTMLElement;
    await user.selectOptions(within(calendar).getByLabelText("Dal giorno"), "SATURDAY");
    await user.selectOptions(within(calendar).getByLabelText("Al giorno"), "SATURDAY");

    await user.selectOptions(screen.getByLabelText("Calendario di lavoro · Ufficio"), "cal-1");
    expect(current().resources[0].calendarId).toBe("cal-1");
    expect(current().calendars?.[0]).toMatchObject({ name: "Turno sabato", periods: [{ from_day: "SATURDAY", to_day: "SATURDAY", begin: "09:00", end: "17:00" }] });

    await user.click(screen.getByRole("button", { name: "Rimuovi calendario Turno sabato" }));
    expect(current().calendars).toEqual([]);
    expect(current().resources[0].calendarId).toBeUndefined();
    expect(screen.getByLabelText("Calendario di lavoro · Ufficio")).toHaveValue("");
  });

  it("does not run with a period across midnight", async () => {
    render(<Harness initial={{ ...READY, calendars: [{ id: "cal-1", name: "Notte", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "22:00", end: "06:00" }] }] }} />);

    expect(screen.getByRole("alert")).toHaveTextContent("va diviso in due periodi");
    expect(screen.getByRole("button", { name: "Avvia simulazione" })).toBeDisabled();
    expect(screen.getByText("Calendari da correggere: 1")).toBeInTheDocument();
  });
});
