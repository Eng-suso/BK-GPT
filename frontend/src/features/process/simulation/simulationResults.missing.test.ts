import { describe, expect, it } from "vitest";

import {
  MISSING_VALUE,
  formatCurrency,
  formatDuration,
  formatOrMissing,
  formatPercent,
} from "./simulationResults";

/**
 * U3. Il Cruscotto leggeva ogni KPI con `?? 0`, quindi una simulazione senza
 * indicatori si presentava come una simulazione con tempo di ciclo zero e costo
 * zero. In un prodotto di consulenza quei numeri finiscono in una slide.
 */
describe("un KPI che manca non e' un KPI che vale zero", () => {
  it("scrive il trattino quando il valore non c'e'", () => {
    expect(formatOrMissing(undefined, (v) => formatDuration(v, "it"))).toBe(MISSING_VALUE);
    expect(formatOrMissing(null, formatPercent)).toBe(MISSING_VALUE);
  });

  it("scrive il trattino anche quando il valore non e' un numero vero", () => {
    // Un JSON storto o una divisione per zero a monte arrivano cosi'.
    expect(formatOrMissing(Number.NaN, formatPercent)).toBe(MISSING_VALUE);
    expect(formatOrMissing(Number.POSITIVE_INFINITY, (v) => formatCurrency(v, "it"))).toBe(
      MISSING_VALUE,
    );
  });

  it("uno zero vero resta zero", () => {
    // La distinzione serve in tutte e due le direzioni: una coda vuota e' un
    // risultato, e deve leggersi come tale.
    expect(formatOrMissing(0, formatPercent)).toBe("0%");
    expect(formatOrMissing(0, (v) => formatDuration(v, "it"))).toBe("0 s");
  });

  it("formatta normalmente quando il valore c'e'", () => {
    expect(formatOrMissing(0.42, formatPercent)).toBe("42%");
    expect(formatOrMissing(3600, (v) => formatDuration(v, "it"))).toBe("1h");
  });
});
