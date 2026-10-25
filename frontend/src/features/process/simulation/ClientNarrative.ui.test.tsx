import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { HttpError } from "@/lib/http";

import { ClientNarrative } from "./ClientNarrative";
import type { SimulationNarrativeRequest } from "./simulationTypes";

const writeSimulationNarrative = vi.fn();
// Un rifiuto passa fuori dal vi.fn: il suo tracciamento delle promesse lo segnalerebbe come non gestito.
let failWith: Error | null = null;
vi.mock("./simulationApi", () => ({
  writeSimulationNarrative: (...args: unknown[]) => (failWith ? Promise.reject(failWith) : writeSimulationNarrative(...args)),
}));

const request: SimulationNarrativeRequest = {
  language: "it", as_is_name: "AS-IS", scenario_name: "A · +1", reading: [], names: [],
  kpis: [{ label: "Durata", value: "−1 h ± 10 min", verdict: "better" }],
};

function setup(text: string | null = null) {
  const onWritten = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <ClientNarrative bpmnModelId="m1" name="A · +1" request={request} text={text} onWritten={onWritten} />
    </QueryClientProvider>,
  );
  return onWritten;
}

describe("ClientNarrative (SIM-24b)", () => {
  beforeEach(() => {
    writeSimulationNarrative.mockReset();
    failWith = null;
  });

  it("asks for the text only when the consultant clicks, then hands it up", async () => {
    writeSimulationNarrative.mockResolvedValue({ text: "Un caso dura −1 h ± 10 min in meno.", cited: ["K1"] });
    const onWritten = setup();
    expect(writeSimulationNarrative).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Scrivi il testo per il cliente · A · +1" }));

    await waitFor(() => expect(onWritten).toHaveBeenCalledWith("Un caso dura −1 h ± 10 min in meno."));
    expect(writeSimulationNarrative).toHaveBeenCalledWith("m1", request);
  });

  it("shows the text with where its numbers come from, and offers to rewrite it", () => {
    setup("Un caso dura −1 h ± 10 min in meno.");
    const figure = screen.getByRole("figure", { name: "Testo per il cliente di A · +1" });
    expect(figure.textContent).toMatch(/ogni numero viene dai run/);
    expect(screen.getByRole("button", { name: "Riscrivi · A · +1" })).toBeTruthy();
  });

  it("says why when the text could not be verified", async () => {
    failWith = new HttpError(502, "Bad Gateway", {
      error: { message: "Il testo del modello contiene numeri non verificabili: resta la lettura calcolata." },
    });
    const onWritten = setup();
    fireEvent.click(screen.getByRole("button", { name: /Scrivi il testo per il cliente/ }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/numeri non verificabili/));
    expect(onWritten).not.toHaveBeenCalled();
  });
});
