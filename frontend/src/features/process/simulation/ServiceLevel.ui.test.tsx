import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import type { CaseAttributeDraft } from "./caseRules";
import { ServiceLevelFields, ServiceLevelOutcome } from "./ServiceLevel";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type SlaDraft } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

const TIPO: CaseAttributeDraft = { id: "a1", name: "tipo", kind: "category", categories: [{ value: "premium", percent: 20 }, { value: "standard", percent: 80 }] };

function Harness({ attributes = [], initial }: { attributes?: CaseAttributeDraft[]; initial?: SlaDraft }) {
  const [sla, setSla] = React.useState<SlaDraft | undefined>(initial);
  return (
    <>
      <ServiceLevelFields sla={sla} attributes={attributes} onChange={setSla} />
      <output data-testid="sla">{JSON.stringify(sla ?? null)}</output>
    </>
  );
}

const current = (): SlaDraft | null => JSON.parse(screen.getByTestId("sla").textContent ?? "null");

describe("service objective (SIM-13)", () => {
  it("adds an objective, reads it as a sentence and sends it in seconds", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Aggiungi un obiettivo di servizio" }));
    expect(screen.getByText("Almeno il 90% dei casi deve chiudersi entro 2 giorni.")).toBeInTheDocument();

    const share = screen.getByLabelText("Quota minima di casi, %");
    await user.clear(share);
    await user.type(share, "0");
    expect(screen.getByRole("alert")).toHaveTextContent("La quota va da 1 a 100.");

    await user.clear(share);
    await user.type(share, "80");
    const sla = current()!;
    const draft = { ...structuredClone(DEFAULT_SCENARIO), sla };
    expect(scenarioToInput(draft, null).sla).toEqual({ targetSeconds: 2 * 86_400, share: 0.8 });
    expect(scenarioParameterIssues(draft).sla).toBe(false);

    await user.click(screen.getByRole("button", { name: "Togli l'obiettivo" }));
    expect(current()).toBeNull();
  });

  it("tells whether the run met the objective", () => {
    const run = { summary: { sla: { target_seconds: 172_800, share_target: 0.9, share_within: 0.87, cases: 100, late_cases: 13, met: false } } } as unknown as SimulationRun;
    render(<ServiceLevelOutcome run={run} />);
    const outcome = screen.getByRole("region", { name: "Obiettivo di servizio" });
    expect(within(outcome).getByText("Non rispettato")).toBeInTheDocument();
    expect(outcome).toHaveTextContent("87% dei casi chiusi entro 2g (obiettivo 90%).");
    expect(outcome).toHaveTextContent("13 casi su 100 oltre il tempo.");
  });

  it("needs a category attribute before offering objectives by group", () => {
    render(<Harness initial={{ target: 2, unit: "days", sharePercent: 90 }} />);
    expect(screen.getByText(/aggiungi un attributo a categorie/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aggiungi un obiettivo per gruppo" })).not.toBeInTheDocument();
  });

  it("gives a group of cases its own objective (SIM-13b)", async () => {
    const user = userEvent.setup();
    render(<Harness attributes={[TIPO]} initial={{ target: 3, unit: "days", sharePercent: 90 }} />);
    await user.click(screen.getByRole("button", { name: "Aggiungi un obiettivo per gruppo" }));
    expect(screen.getByLabelText("Casi · Gruppo 1")).toHaveValue("a1\u0000premium");

    await user.selectOptions(screen.getByLabelText("Unità · tipo = premium"), "hours");
    const target = screen.getByLabelText("Entro · tipo = premium");
    await user.clear(target);
    await user.type(target, "24");
    expect(screen.getByText("Almeno il 90% dei casi tipo = premium deve chiudersi entro 24 ore.")).toBeInTheDocument();
    expect(current()?.segments).toEqual([{ attributeId: "a1", value: "premium", target: 24, unit: "hours", sharePercent: 90 }]);

    // Il secondo gruppo parte dalla categoria libera; scegliere la stessa e' un errore.
    await user.click(screen.getByRole("button", { name: "Aggiungi un obiettivo per gruppo" }));
    expect(screen.getByLabelText("Casi · Gruppo 2")).toHaveValue("a1\u0000standard");
    expect(screen.getByRole("button", { name: "Aggiungi un obiettivo per gruppo" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Casi · Gruppo 2"), "a1\u0000premium");
    expect(screen.getByRole("alert")).toHaveTextContent("Questo gruppo ha già un obiettivo.");

    await user.click(screen.getAllByRole("button", { name: "Togli l'obiettivo di tipo = premium" })[1]);
    await user.click(screen.getByRole("button", { name: "Togli l'obiettivo di tipo = premium" }));
    expect(current()?.segments).toBeUndefined();
  });

  it("tells the outcome of each group, and says when a group had no cases", () => {
    const run = { summary: { sla: {
      target_seconds: 172_800, share_target: 0.9, share_within: 0.95, cases: 100, late_cases: 5, met: true,
      segments: [
        { attribute: "tipo", value: "premium", target_seconds: 86_400, share_target: 0.95, share_within: 0.8, cases: 20, late_cases: 4, met: false },
        { attribute: "tipo", value: "gold", target_seconds: 3600, share_target: 0.5, share_within: 0, cases: 0, late_cases: 0, met: false },
      ],
    } } } as unknown as SimulationRun;
    render(<ServiceLevelOutcome run={run} />);
    const groups = screen.getByRole("list", { name: "Obiettivi per gruppo di casi" });
    const [premium, gold] = within(groups).getAllByRole("listitem");
    expect(within(premium).getByText("Non rispettato")).toBeInTheDocument();
    expect(premium).toHaveTextContent("80% entro 1g (obiettivo 95%): 4 casi su 20 oltre il tempo.");
    expect(gold).toHaveTextContent("Nessun caso nel run");
  });
});
