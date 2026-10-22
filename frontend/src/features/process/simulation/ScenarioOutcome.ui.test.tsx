import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { ScenarioOutcomes } from "./ScenarioOutcome";
import type { ScenarioRuns, WorkspaceScenario } from "./scenarioWorkspace";

const scenario = (outcome?: WorkspaceScenario["outcome"]): WorkspaceScenario => ({
  id: 2, kind: "alternative", label: "A", name: "+1 approvatore", revision: 1, draft: {}, patch: [], conflicts: [],
  created_at: "", updated_at: "", outcome,
});
const results = { latest: { id: 9 }, members: [], completed: [{ id: 9 }], status: "current", bpmnChanged: false } as unknown as ScenarioRuns;

const OUTCOME: NonNullable<WorkspaceScenario["outcome"]> = {
  implemented_on: "2026-01-10", recorded_at: "2026-02-01T00:00:00Z", as_is_run_id: 1, alternative_run_id: 2,
  before: { event_log_id: "l", name: "erp.csv", cases: 3 }, after: { event_log_id: "l", name: "erp.csv", cases: 3 },
  kpis: [
    { kpi: "cycle", predicted_change: -0.4, predicted_low: -0.5, predicted_high: -0.3, before: 7200, after: 3600, observed_change: -0.5, error: -0.1, within: true },
    { kpi: "costPerCase", predicted_change: -0.2, before: null, after: null, observed_change: null, error: null, within: null },
  ],
};

function mount(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("previsto contro osservato (SIM-28)", () => {
  it("un'alternativa implementata dice previsto, osservato e scarto per KPI", () => {
    const onRecord = vi.fn().mockResolvedValue(true);
    mount(<ScenarioOutcomes processId="p" asIs={results} lang="it" onRecord={onRecord}
      alternatives={[{ scenario: scenario(OUTCOME), results, comparison: null }]} />);

    expect(screen.getByText(/A · \+1 approvatore · implementata il 10\/0?1\/2026/)).toBeInTheDocument();
    const table = screen.getByRole("region", { name: "Previsto contro osservato · A · +1 approvatore" });
    const cycle = within(table).getByRole("row", { name: /Durata|Cycle|tempo/i });
    expect(cycle).toHaveTextContent("-40% (da -50% a -30%)");
    expect(cycle).toHaveTextContent("-50%");
    expect(cycle).toHaveTextContent("-10 punti");
    expect(cycle).toHaveTextContent("Dentro l'intervallo previsto");
    expect(table).toHaveTextContent("Il log non lo misura");

    fireEvent.click(screen.getByRole("button", { name: "Togli l'esito di A · +1 approvatore" }));
    expect(onRecord).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }), null);
  });

  it("senza un log mappato chiede di importarlo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
    mount(<ScenarioOutcomes processId="p" asIs={results} lang="it" onRecord={vi.fn()}
      alternatives={[{ scenario: scenario(null), results, comparison: { kpis: { cycle: null, waiting: null, costPerCase: null, throughput: null }, paired: null, mismatch: false } }]} />);

    fireEvent.click(screen.getByRole("button", { name: "Registra l'implementazione di A · +1 approvatore" }));
    expect(await screen.findByText(/Serve un log reale mappato/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Misura" })).toBeDisabled();
    vi.unstubAllGlobals();
  });
});
