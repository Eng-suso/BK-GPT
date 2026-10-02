import { describe, expect, it } from "vitest";

import { overlapsPeriod, periodRange } from "./periods";

const NOW = new Date(2026, 4, 20); // 20 maggio 2026

describe("periodRange", () => {
  it("covers the calendar month, quarter and year the consultant is in", () => {
    expect(periodRange("month", NOW)).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(periodRange("quarter", NOW)).toEqual({ from: "2026-04-01", to: "2026-06-30" });
    expect(periodRange("year", NOW)).toEqual({ from: "2026-01-01", to: "2026-12-31" });
  });

  it("does not bound anything when no period is chosen", () => {
    expect(periodRange("all", NOW)).toEqual({ from: null, to: null });
  });
});

describe("overlapsPeriod", () => {
  const quarter = periodRange("quarter", NOW);

  it("keeps a long engagement that is still open", () => {
    // Filtrando per data di inizio, i progetti lunghi - quelli che contano -
    // sparirebbero dal trimestre in cui si sta lavorando.
    expect(overlapsPeriod({ startDate: "2026-01-10", endDate: "2026-09-30" }, quarter)).toBe(true);
  });

  it("drops what ends before and what starts after", () => {
    expect(overlapsPeriod({ startDate: "2025-01-01", endDate: "2025-12-31" }, quarter)).toBe(false);
    expect(overlapsPeriod({ startDate: "2026-07-01", endDate: "2026-08-31" }, quarter)).toBe(false);
  });

  it("keeps an engagement with no dates: 'not said' is not 'out of period'", () => {
    expect(overlapsPeriod({ startDate: null, endDate: null }, quarter)).toBe(true);
  });

  it("keeps an open-ended engagement that has already started", () => {
    expect(overlapsPeriod({ startDate: "2026-02-01", endDate: null }, quarter)).toBe(true);
    expect(overlapsPeriod({ startDate: null, endDate: "2026-05-05" }, quarter)).toBe(true);
  });

  it("keeps everything when no period is chosen", () => {
    const all = periodRange("all", NOW);
    expect(overlapsPeriod({ startDate: "2020-01-01", endDate: "2020-02-01" }, all)).toBe(true);
  });
});
