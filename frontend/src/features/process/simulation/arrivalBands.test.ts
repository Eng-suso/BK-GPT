import { describe, expect, it } from "vitest";

import { BAND_ATTRIBUTE_ID, arrivalBandIssues, newArrivalBand, withBandAttribute, type ArrivalBandDraft } from "./arrivalBands";
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

describe("arrival band as a case attribute (SIM-33)", () => {
  const two = [newArrivalBand([]), newArrivalBand([newArrivalBand([])])];
  const tipo = { id: "attr-1", name: "tipo", kind: "category" as const, categories: [{ value: "premium", percent: 100 }] };

  it("adds the attribute with one category per band, and keeps the others", () => {
    const attributes = withBandAttribute([tipo], two, true);
    expect(attributes[0]).toBe(tipo);
    expect(attributes[1]).toEqual({ id: BAND_ATTRIBUTE_ID, name: "fascia_arrivo", kind: "category",
      categories: [{ value: "Fascia 1", percent: 50 }, { value: "Fascia 2", percent: 50 }] });
  });

  it("follows the bands and goes away when switched off or without bands", () => {
    const withTwo = withBandAttribute([tipo], two, true);
    const withOne = withBandAttribute(withTwo, two.slice(0, 1), true);
    expect(withOne[1]).toMatchObject({ categories: [{ value: "Fascia 1", percent: 100 }] });
    expect(withBandAttribute(withOne, two, false)).toEqual([tipo]);
    expect(withBandAttribute(withOne, undefined, true)).toEqual([tipo]);
    const untouched = [tipo];
    expect(withBandAttribute(untouched, two, false)).toBe(untouched);
  });

  it("sends the attribute name with the bands, and only with them", () => {
    const draft = { ...DEFAULT_SCENARIO, arrival: { distribution: "expon" as const, bands: two, bandAttribute: true } };
    expect(scenarioToInput(draft, null).arrival?.bandAttribute).toBe("fascia_arrivo");
    const noBands = { ...DEFAULT_SCENARIO, arrival: { distribution: "expon" as const, bandAttribute: true } };
    expect(scenarioToInput(noBands, null).arrival?.bandAttribute).toBeUndefined();
  });
});
