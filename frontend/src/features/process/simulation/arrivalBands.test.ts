import { describe, expect, it } from "vitest";

import { arrivalBandIssues, newArrivalBand, type ArrivalBandDraft } from "./arrivalBands";
import { DEFAULT_SCENARIO, parseScenarioDraft, scenarioParameterIssues, scenarioToInput, withArrival, arrivalDuration } from "./simulationScenario";

const PEAK: ArrivalBandDraft = { fromDay: "MONDAY", toDay: "FRIDAY", begin: "09:00", end: "12:00", meanMinutes: 5 };
const QUIET: ArrivalBandDraft = { fromDay: "MONDAY", toDay: "FRIDAY", begin: "14:00", end: "17:00", meanMinutes: 30 };

describe("arrivi per fascia oraria (SIM-08)", () => {
  it("manda le fasce con il tempo medio in secondi", () => {
    const draft = { ...structuredClone(DEFAULT_SCENARIO), arrival: { distribution: "expon" as const, bands: [PEAK, QUIET] } };
    expect(scenarioToInput(draft, null).arrival?.bands).toEqual([
      { fromDay: "MONDAY", toDay: "FRIDAY", begin: "09:00", end: "12:00", meanSeconds: 300 },
      { fromDay: "MONDAY", toDay: "FRIDAY", begin: "14:00", end: "17:00", meanSeconds: 1800 },
    ]);
  });

  it("trova orari invertiti, medie non positive e fasce che si sovrappongono, anche fra giorni diversi", () => {
    expect(arrivalBandIssues([PEAK, QUIET])).toEqual([null, null]);
    expect(arrivalBandIssues([{ ...PEAK, begin: "12:00", end: "09:00" }])).toEqual(["order"]);
    expect(arrivalBandIssues([{ ...PEAK, meanMinutes: 0 }])).toEqual(["mean"]);
    expect(arrivalBandIssues([PEAK, { ...PEAK, fromDay: "FRIDAY", toDay: "SUNDAY", begin: "11:00", end: "13:00" }])).toEqual([null, "overlap"]);
    expect(arrivalBandIssues([PEAK, { ...PEAK, fromDay: "SATURDAY", toDay: "SUNDAY" }])).toEqual([null, null]);
  });

  it("una fascia da correggere blocca il run", () => {
    const draft = { ...structuredClone(DEFAULT_SCENARIO), arrival: { distribution: "expon" as const, bands: [PEAK, PEAK] } };
    expect(scenarioParameterIssues(draft).arrival).toBe(true);
  });

  it("cambiare la distribuzione degli arrivi non perde le fasce, e una bozza salvata le rilegge", () => {
    const draft = { ...structuredClone(DEFAULT_SCENARIO), arrival: { distribution: "expon" as const, bands: [PEAK] } };
    const next = withArrival(draft, { ...arrivalDuration(draft), meanMinutes: 20 });
    expect(next.arrival?.bands).toEqual([PEAK]);
    expect(parseScenarioDraft({ arrival: { distribution: "expon", bands: [PEAK, { fromDay: "MAI" }] } }).arrival?.bands).toEqual([PEAK]);
  });

  it("propone il picco del mattino e poi il pomeriggio", () => {
    expect(newArrivalBand([])).toMatchObject({ begin: "09:00", meanMinutes: 5 });
    expect(newArrivalBand([PEAK])).toMatchObject({ begin: "14:00", meanMinutes: 30 });
  });
});
