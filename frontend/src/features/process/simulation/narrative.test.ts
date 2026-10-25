import { describe, expect, it } from "vitest";

import { narrativeRequest } from "./narrative";
import type { ScenarioDelta } from "./scenarioWorkspace";

const interval = (delta: number, verdict: "better" | "worse" | "unclear"): ScenarioDelta =>
  ({ kind: "interval", paired: true, value: { a: 0, b: 0, delta, half: 60, verdict, probBetter: 0.9, comparisons: 1 } }) as unknown as ScenarioDelta;

const base = {
  language: "it" as const,
  asIsName: "AS-IS",
  scenarioName: "A · +1 Approvatore",
  kpis: ["cycle", "waiting", "costPerCase", "throughput"] as const,
  label: (kpi: string) => ({ cycle: "Durata", waiting: "Attesa", costPerCase: "Costo per caso", throughput: "Casi all'ora" })[kpi]!,
  value: (_kpi: string, delta: ScenarioDelta) => (delta.kind === "interval" ? `${delta.value.delta} ± ${delta.value.half}` : `${delta.delta}`),
  reading: ["Il vincolo resta Approva."],
  names: ["Approva", "Paga", "Approva", ""],
};

describe("narrativeRequest (SIM-24b)", () => {
  it("sends each measured KPI with its formatted value and verdict, in the table order", () => {
    const request = narrativeRequest({
      ...base,
      kpis: [...base.kpis],
      deltas: { cycle: interval(-3600, "better"), waiting: null, costPerCase: interval(4, "unclear"),
        throughput: { kind: "single", delta: 0.5, direction: "better" } },
    });
    expect(request).toEqual({
      language: "it",
      as_is_name: "AS-IS",
      scenario_name: "A · +1 Approvatore",
      kpis: [
        { label: "Durata", value: "-3600 ± 60", verdict: "better" },
        { label: "Costo per caso", value: "4 ± 60", verdict: "unclear" },
        { label: "Casi all'ora", value: "0.5", verdict: "better" },
      ],
      reading: ["Il vincolo resta Approva."],
      names: ["Approva", "Paga"],
    });
  });

  it("with no measured difference there is nothing to write", () => {
    expect(narrativeRequest({ ...base, kpis: [...base.kpis], deltas: { cycle: null } })).toBeNull();
  });
});
