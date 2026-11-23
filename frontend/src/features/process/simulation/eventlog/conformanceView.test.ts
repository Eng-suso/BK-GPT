import { describe, expect, it } from "vitest";

import { adherence, deviationRows, offPathVariants } from "./conformanceView";
import { CONFORMANCE } from "./conformanceFixture";

describe("conformance view", () => {
  it("bands adherence like the real-vs-simulated verdict", () => {
    expect(adherence(0.95)).toBe("close");
    expect(adherence(0.7)).toBe("calibrate");
    expect(adherence(0.2)).toBe("far");
  });

  it("shows only named steps, with the share of cases they touch", () => {
    const rows = deviationRows(CONFORMANCE);
    expect(rows.map((row) => row.name)).toEqual(["Approvazione CFO", "Emissione ordine"]);
    expect(rows[0]).toMatchObject({ skipped: 3, outOfOrder: 0, share: 0.3 });
  });

  it("explains each off-path variant with the names of the skipped and early steps", () => {
    const [variant, ...rest] = offPathVariants(CONFORMANCE);
    expect(rest).toEqual([]);
    expect(variant).toEqual({
      steps: ["Richiesta", "Emissione ordine"],
      cases: 3,
      skipped: ["Approvazione CFO"],
      early: ["Emissione ordine"],
      unmodeled: [],
    });
  });
});
