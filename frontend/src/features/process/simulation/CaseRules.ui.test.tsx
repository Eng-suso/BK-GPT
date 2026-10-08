import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { DEFAULT_SCENARIO, scenarioToInput, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE: ScenarioTemplate = {
  resources: [],
  standard_calendar: { id: "std", name: "Standard", periods: [{ from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" }] },
  tasks: [{ element_id: "T1", name: "Verifica", type: "userTask" }],
  gateways: [{
    element_id: "G_split",
    name: "Importo alto?",
    type: "exclusiveGateway",
    branches: [
      { flow_id: "F_high", flow_name: "", target_name: "Approva" },
      { flow_id: "F_low", flow_name: "", target_name: "Paga" },
    ],
  }],
} as unknown as ScenarioTemplate;

const READY: ScenarioDraft = {
  ...structuredClone(DEFAULT_SCENARIO),
  resources: [{ id: "r1", name: "Ufficio", costPerHour: 30, amount: 2, parametersConfirmed: true }],
  tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
  gateways: { G_split: { F_high: 50, F_low: 50 } },
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
const runButton = () => screen.getByRole("button", { name: "Avvia simulazione" });

describe("case attributes and branch rules in the scenario panel", () => {
  it("routes a decision by an amount threshold and sends it as a model patch", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);

    const byRule = screen.getByRole("button", { name: "Per regola" });
    expect(byRule).toBeDisabled();
    expect(screen.getByText(/definisci prima un attributo del caso/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aggiungi attributo" }));
    const name = screen.getByLabelText("Nome dell'attributo");
    await user.clear(name);
    await user.type(name, "importo");
    await user.click(screen.getByRole("button", { name: "Numero" }));
    await user.clear(screen.getByLabelText("Minimo"));
    await user.type(screen.getByLabelText("Minimo"), "100");
    await user.clear(screen.getByLabelText("Massimo"));
    await user.type(screen.getByLabelText("Massimo"), "12000");

    await user.click(screen.getByRole("button", { name: "Per regola" }));
    const high = screen.getByRole("group", { name: "Verso Approva" });
    await user.type(within(high).getByLabelText("Valore per importo"), "5000");
    const low = screen.getByRole("group", { name: "Verso Paga" });
    await user.selectOptions(within(low).getByLabelText("Confronto su importo"), "<=");
    await user.type(within(low).getByLabelText("Valore per importo"), "5000");

    expect(within(high).getByText("Il caso va qui se importo > 5000.")).toBeInTheDocument();
    expect(runButton()).toBeEnabled();
    expect(screen.getByRole("button", { name: "Togli l'attributo importo" })).toBeDisabled();
    expect(screen.getByText("Usato da 1 decisione: toglilo prima dalla regola.")).toBeInTheDocument();

    const patch = scenarioToInput(current(), null).modelPatch;
    expect(patch?.case_attributes).toEqual([{ name: "importo", distribution: { kind: "uniform", minimum: 100, maximum: 12000 }, provenance: { origin: "manual" } }]);
    expect(patch?.gateways?.[0].branches.map((b) => b.condition.any_of[0][0])).toEqual([
      { attribute: "importo", operator: ">", value: 5000 },
      { attribute: "importo", operator: "<=", value: 5000 },
    ]);
  });

  it("blocks the run until every branch has a complete rule, and back to percentages drops the rules", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{
      ...READY,
      caseAttributes: [{ id: "attr-1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 30 }, { value: "standard", percent: 70 }] }],
    }} />);

    await user.click(screen.getByRole("button", { name: "Per regola" }));
    const low = screen.getByRole("group", { name: "Verso Paga" });
    await user.click(within(low).getByRole("button", { name: "Togli la condizione su tipo" }));
    expect(within(low).getByRole("alert")).toHaveTextContent("Ogni ramo ha bisogno di almeno una regola.");
    expect(runButton()).toBeDisabled();
    expect(screen.getByText("Decisioni per regola da completare: 1")).toBeInTheDocument();

    await user.click(within(low).getByRole("button", { name: "Aggiungi regola" }));
    await user.selectOptions(within(low).getByLabelText("Valore per tipo"), "standard");
    expect(within(low).getByText("Il caso va qui se tipo = standard.")).toBeInTheDocument();
    expect(runButton()).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Per percentuale" }));
    expect(current().gatewayRules).toEqual({});
    expect(screen.getByLabelText("Approva")).toHaveValue(50);
  });

  it("says what an attribute is missing", async () => {
    const user = userEvent.setup();
    render(<Harness initial={READY} />);
    await user.click(screen.getByRole("button", { name: "Aggiungi attributo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Ogni categoria ha un nome, diverso dalle altre.");
    expect(runButton()).toBeDisabled();
    await user.type(screen.getByLabelText("Categoria 1"), "premium");
    await user.type(screen.getByLabelText("Categoria 2"), "standard");
    await user.clear(screen.getAllByRole("spinbutton", { name: "Quota" })[0]);
    await user.type(screen.getAllByRole("spinbutton", { name: "Quota" })[0], "30");
    expect(screen.getByRole("alert")).toHaveTextContent("sommare 100%");
    await user.clear(screen.getAllByRole("spinbutton", { name: "Quota" })[1]);
    await user.type(screen.getAllByRole("spinbutton", { name: "Quota" })[1], "70");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(runButton()).toBeEnabled();
  });
});
