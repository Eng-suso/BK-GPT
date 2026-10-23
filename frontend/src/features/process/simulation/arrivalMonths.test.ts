import { describe, expect, it } from "vitest";

import { arrivalMonthIssues, arrivalMonthsInput, monthsNeedPoisson, newArrivalMonth, sanitizeArrivalMonths } from "./arrivalMonths";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type ScenarioDraft } from "./simulationScenario";

function draft(arrival: ScenarioDraft["arrival"]): ScenarioDraft {
  return { ...structuredClone(DEFAULT_SCENARIO), arrival };
}

describe("ritmo degli arrivi per mese (SIM-08b)", () => {
  it("manda la variazione come fattore sul ritmo", () => {
    expect(arrivalMonthsInput([{ month: 12, percent: 40 }, { month: 8, percent: -50 }])).toEqual([
      { month: 12, factor: 1.4 }, { month: 8, factor: 0.5 },
    ]);
    const input = scenarioToInput(draft({ distribution: "expon", months: [{ month: 12, percent: 40 }] }), null);
    expect(input.arrival?.months).toEqual([{ month: 12, factor: 1.4 }]);
    expect(scenarioToInput(draft({ distribution: "expon" }), null).arrival).not.toHaveProperty("months");
  });

  it("propone il primo mese libero, partendo da dicembre", () => {
    expect(newArrivalMonth([])).toEqual({ month: 12, percent: 20 });
    expect(newArrivalMonth([{ month: 12, percent: 20 }]).month).toBe(1);
  });

  it("blocca un mese ripetuto o una variazione impossibile", () => {
    expect(arrivalMonthIssues([{ month: 12, percent: 40 }, { month: 12, percent: 10 }])).toEqual([null, "duplicate"]);
    expect(arrivalMonthIssues([{ month: 5, percent: -100 }, { month: 6, percent: 901 }, { month: 13, percent: 0 }]))
      .toEqual(["percent", "percent", "month"]);
    expect(scenarioParameterIssues(draft({ distribution: "expon", months: [{ month: 5, percent: -100 }] })).arrival).toBe(true);
  });

  it("senza fasce vuole arrivi esponenziali", () => {
    expect(monthsNeedPoisson([{ month: 12, percent: 40 }], false, "norm")).toBe(true);
    expect(monthsNeedPoisson([{ month: 12, percent: 40 }], true, "norm")).toBe(false);
    expect(monthsNeedPoisson([{ month: 12, percent: 40 }], false, "expon")).toBe(false);
    expect(scenarioParameterIssues(draft({ distribution: "norm", months: [{ month: 12, percent: 40 }] })).arrival).toBe(true);
    expect(scenarioParameterIssues(draft({ distribution: "expon", months: [{ month: 12, percent: 40 }] })).arrival).toBe(false);
  });

  it("scarta i mesi salvati male", () => {
    expect(sanitizeArrivalMonths([{ month: "maggio", percent: 10 }, { month: 3, percent: 5 }])).toEqual([{ month: 3, percent: 5 }]);
    expect(sanitizeArrivalMonths("rotto")).toBeUndefined();
    expect(sanitizeArrivalMonths([])).toBeUndefined();
  });
});
