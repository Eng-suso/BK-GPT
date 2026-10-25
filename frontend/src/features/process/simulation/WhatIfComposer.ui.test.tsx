import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { HttpError } from "@/lib/http";

import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";
import { WhatIfComposer } from "./WhatIfComposer";

const translateWhatIf = vi.fn();
// Un rifiuto passa fuori dal vi.fn: il suo tracciamento delle promesse lo segnalerebbe come non gestito.
let failWith: Error | null = null;
vi.mock("./simulationApi", () => ({
  translateWhatIf: (...args: unknown[]) => (failWith ? Promise.reject(failWith) : translateWhatIf(...args)),
}));

const draft = {
  scenarioName: "Base",
  arrivalIntervalMinutes: 30,
  resources: [{ id: "r1", name: "Approvatore", costPerHour: 40, amount: 2, parametersConfirmed: true }],
  tasks: { T: { meanMinutes: 20, distribution: "norm", resourceId: "r1" } },
  gateways: {},
} as unknown as ScenarioDraft;
const template = { tasks: [{ element_id: "T", name: "Verifica" }], gateways: [] } as unknown as ScenarioTemplate;

function setup() {
  const onApply = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <WhatIfComposer bpmnModelId="m1" template={template} draft={draft} onApply={onApply} />
    </QueryClientProvider>,
  );
  const field = screen.getByRole("textbox", { name: "Cosa vuoi provare" });
  const ask = (text: string) => {
    fireEvent.change(field, { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Traduci" }));
  };
  return { onApply, ask };
}

describe("WhatIfComposer (SIM-23)", () => {
  beforeEach(() => {
    translateWhatIf.mockReset();
    failWith = null;
  });

  it("sends the sentence with the activity and role names, then previews the changes", async () => {
    translateWhatIf.mockResolvedValue({
      changes: [{ kind: "resource_units", resource_id: "r1", units: 3 }],
      not_understood: "anche il sabato",
      rejected: 1,
    });
    const { onApply, ask } = setup();
    ask("Un approvatore in più e lavoriamo anche il sabato");

    expect(await screen.findByText("Modifiche proposte")).toBeTruthy();
    expect(translateWhatIf).toHaveBeenCalledWith("m1", {
      sentence: "Un approvatore in più e lavoriamo anche il sabato",
      activities: [{ id: "T", name: "Verifica" }],
      resources: [{ id: "r1", name: "Approvatore", units: 2 }],
    });
    expect(screen.getByText(/Approvatore · .*: 2 → 3/)).toBeTruthy();
    expect(screen.getByText(/Non tradotto: «anche il sabato»/)).toBeTruthy();
    expect(screen.getByText(/1 modifica scartata/)).toBeTruthy();
    // Nessun run e nessuna modifica finché il consulente non applica.
    expect(onApply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Applica alla bozza" }));
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0]?.[0].resources[0]).toMatchObject({ amount: 3, parametersConfirmed: false });
    expect(screen.getByRole("status").textContent).toMatch(/Modifiche applicate/);
    expect(screen.queryByText("Modifiche proposte")).toBeNull();
  });

  it("discarding leaves the draft as it was", async () => {
    translateWhatIf.mockResolvedValue({ changes: [{ kind: "demand", factor: 1.2 }], not_understood: null, rejected: 0 });
    const { onApply, ask } = setup();
    ask("20% di casi in più");
    fireEvent.click(await screen.findByRole("button", { name: "Scarta" }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.queryByText("Modifiche proposte")).toBeNull();
  });

  it("with nothing to change the apply button stays off", async () => {
    translateWhatIf.mockResolvedValue({ changes: [], not_understood: "fai festa", rejected: 0 });
    const { ask } = setup();
    ask("fai festa");
    expect(await screen.findByText(/Nessuna modifica da applicare/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Applica alla bozza" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says why when the model is not available", async () => {
    failWith = new HttpError(503, "Service Unavailable", {
      error: { message: "Il what-if in linguaggio naturale richiede la chiave del modello." },
    });
    const { ask } = setup();
    ask("un approvatore in più");
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/richiede la chiave del modello/));
  });

  it("an empty sentence cannot be sent", () => {
    setup();
    expect((screen.getByRole("button", { name: "Traduci" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
