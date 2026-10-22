import { describe, expect, it } from "vitest";

import { durationWindowIssues, durationWindowsInput, newDurationWindow, sanitizeDurationWindows, type DurationWindowDraft } from "./durationWindows";

const LATE: DurationWindowDraft = { fromDay: "MONDAY", toDay: "FRIDAY", begin: "16:00", end: "18:00", percent: 30 };

describe("fasce orarie della durata (SIM-33b)", () => {
  it("traduce la percentuale in un fattore sulla durata", () => {
    expect(durationWindowsInput([LATE, { ...LATE, fromDay: "SATURDAY", toDay: "SATURDAY", percent: -25 }]).map((w) => w.factor)).toEqual([1.3, 0.75]);
  });

  it("segnala orari invertiti, variazioni fuori scala e fasce che si sovrappongono, anche oltre la domenica", () => {
    expect(durationWindowIssues([
      { ...LATE, begin: "18:00", end: "16:00" },
      { ...LATE, percent: -99.5 },
      { ...LATE, percent: Number.NaN },
      LATE,
      { ...LATE, fromDay: "FRIDAY", toDay: "MONDAY", begin: "17:00", end: "17:30" },
      { ...LATE, fromDay: "SATURDAY", toDay: "SUNDAY", begin: "08:00", end: "09:00", percent: 900 },
    ])).toEqual(["order", "percent", "percent", null, "overlap", null]);
  });

  it("propone il fine giornata e poi il sabato", () => {
    const first = newDurationWindow([]);
    expect(first).toMatchObject({ begin: "16:00", percent: 30 });
    expect(durationWindowIssues([first, newDurationWindow([first])])).toEqual([null, null]);
  });

  it("da una bozza letta da fuori tiene solo le fasce intere", () => {
    expect(sanitizeDurationWindows([LATE, { ...LATE, fromDay: "MOON" }, { ...LATE, percent: "30" }, null])).toEqual([LATE]);
    expect(sanitizeDurationWindows([null])).toBeUndefined();
    expect(sanitizeDurationWindows("rotto")).toBeUndefined();
  });
});
