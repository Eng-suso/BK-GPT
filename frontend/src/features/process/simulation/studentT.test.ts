import { describe, expect, it } from "vitest";

import { tCdf, tQuantile } from "./studentT";

describe("t di Student", () => {
  it("la CDF e' simmetrica e vale 0,5 nello zero", () => {
    expect(tCdf(0, 5)).toBeCloseTo(0.5, 10);
    expect(tCdf(-1.3, 7) + tCdf(1.3, 7)).toBeCloseTo(1, 10);
  });

  it("ritrova i quantili delle tavole", () => {
    expect(tCdf(12.706, 1)).toBeCloseTo(0.975, 4);
    expect(tCdf(2.776, 4)).toBeCloseTo(0.975, 4);
    expect(tCdf(2.093, 19)).toBeCloseTo(0.975, 4);
    expect(tQuantile(0.975, 4)).toBeCloseTo(2.776, 3);
    expect(tQuantile(0.975, 19)).toBeCloseTo(2.093, 3);
    // Code oltre il 97,5%, come nell'intervallo corretto per piu' confronti.
    expect(tQuantile(0.995, 9)).toBeCloseTo(3.25, 2);
    expect(tQuantile(0.9975, 9)).toBeCloseTo(3.69, 2);
  });

  it("accetta gradi di liberta' non interi (Welch)", () => {
    const q = tQuantile(0.975, 4.5);
    expect(q).toBeLessThan(2.776);
    expect(q).toBeGreaterThan(2.571);
  });
});
