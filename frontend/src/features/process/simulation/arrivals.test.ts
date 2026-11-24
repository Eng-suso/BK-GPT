import { afterEach, describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO,
  arrivalDuration,
  arrivalsRunFaster,
  draftArrivalsRunFaster,
  loadScenarioDraft,
  scenarioParameterIssues,
  scenarioToInput,
  withArrival,
  type ScenarioDraft,
} from "./simulationScenario";

const MORNINGS = { id: "cal-1", name: "Mattine", periods: [{ from_day: "MONDAY" as const, to_day: "FRIDAY" as const, begin: "09:00", end: "12:00" }] };

const draft = (patch: Partial<ScenarioDraft> = {}): ScenarioDraft => ({ ...structuredClone(DEFAULT_SCENARIO), ...patch });

describe("case arrivals in the scenario draft (A2-3)", () => {
  afterEach(() => window.localStorage.clear());

  it("sends the historical exponential when the consultant only sets the mean", () => {
    expect(scenarioToInput(draft({ arrivalIntervalMinutes: 20 }), null).arrival).toEqual({
      meanSeconds: 1200, distribution: "expon", stdSeconds: undefined, minSeconds: undefined, maxSeconds: undefined, calendarId: undefined,
    });
  });

  it("sends the chosen distribution, its bounds and the arrival calendar", () => {
    const next = withArrival(draft({ calendars: [MORNINGS] }), { meanMinutes: 15, distribution: "uniform", minMinutes: 10, maxMinutes: 20 }, "cal-1");
    expect(next.arrivalIntervalMinutes).toBe(15);
    expect(scenarioToInput(next, null).arrival).toEqual({
      meanSeconds: 900, distribution: "uniform", stdSeconds: undefined, minSeconds: 600, maxSeconds: 1200, calendarId: "cal-1",
    });
  });

  it("drops a calendar that no longer exists instead of sending it", () => {
    const next = withArrival(draft(), arrivalDuration(draft()), "gone");
    expect(scenarioToInput(next, null).arrival?.calendarId).toBeUndefined();
  });

  it("goes back to the standard calendar when the consultant picks it again", () => {
    const morning = withArrival(draft({ calendars: [MORNINGS] }), arrivalDuration(draft()), "cal-1");
    const standard = withArrival(morning, arrivalDuration(morning), undefined);
    expect(standard.arrival?.calendarId).toBeUndefined();
    expect(scenarioToInput(standard, null).arrival?.calendarId).toBeUndefined();
    // Senza calendario nell'argomento, quello scelto resta.
    expect(withArrival(morning, { ...arrivalDuration(morning), meanMinutes: 40 }).arrival?.calendarId).toBe("cal-1");
  });

  it("refuses a mean outside the bounds the engine would reject", () => {
    const outside = withArrival(draft({ arrivalIntervalMinutes: 15 }), { meanMinutes: 15, distribution: "expon", minMinutes: 20, maxMinutes: 30 });
    expect(scenarioParameterIssues(outside)).toMatchObject({ arrival: true, ready: false });
    const inside = withArrival(draft(), { meanMinutes: 25, distribution: "expon", minMinutes: 20, maxMinutes: 30 });
    expect(scenarioParameterIssues(inside)).toMatchObject({ arrival: false });
  });

  it("blocks the run while the arrivals need fixing", () => {
    const next = withArrival(draft(), { meanMinutes: 15, distribution: "uniform" });
    expect(scenarioParameterIssues(next)).toMatchObject({ arrival: true, ready: false });
    expect(scenarioParameterIssues(draft())).toMatchObject({ arrival: false });
  });

  it("restores the arrivals from storage and ignores a broken entry", () => {
    window.localStorage.setItem("delir-sim-scenario:m1", JSON.stringify({ arrival: { distribution: "gamma", stdMinutes: 4, calendarId: "cal-1" } }));
    expect(loadScenarioDraft("m1").arrival).toEqual({ distribution: "gamma", stdMinutes: 4, minMinutes: undefined, maxMinutes: undefined, calendarId: "cal-1" });
    window.localStorage.setItem("delir-sim-scenario:m2", JSON.stringify({ arrival: { distribution: "weibull" } }));
    expect(loadScenarioDraft("m2").arrival).toBeUndefined();
  });
});

describe("arrivals the engine makes denser (IMP-01)", () => {
  // Procure_to_Pay: expon [1805, 5, 3600] secondi.
  const procureToPay = { meanMinutes: 1805 / 60, distribution: "expon" as const, minMinutes: 5 / 60, maxMinutes: 60 };

  it("finds the mean Prosimos 2.1 really produces and how many more cases arrive", () => {
    const faster = arrivalsRunFaster(procureToPay);
    expect(faster?.producedSeconds).toBeCloseTo(1240.5, 0);
    expect(faster?.morePercent).toBe(45);
    expect(faster?.suggestedMaxMinutes).toBeCloseTo(150.4, 1);
  });

  it("stays quiet when the maximum is far, on the suggested maximum and for other shapes", () => {
    expect(arrivalsRunFaster({ ...procureToPay, maxMinutes: procureToPay.meanMinutes * 5 })).toBeNull();
    expect(arrivalsRunFaster({ ...procureToPay, maxMinutes: undefined })).toBeNull();
    expect(arrivalsRunFaster({ ...procureToPay, distribution: "fixed" })).toBeNull();
    // Insurance_Claims: expon [17, 16, 3600] secondi, media sul minimo.
    expect(arrivalsRunFaster({ meanMinutes: 17 / 60, distribution: "expon", minMinutes: 16 / 60, maxMinutes: 60 })).toBeNull();
  });
});

describe("the arrivals warning on a whole draft (IMP-01)", () => {
  const denser = { arrivalIntervalMinutes: 1805 / 60, arrival: { distribution: "expon" as const, minMinutes: 5 / 60, maxMinutes: 60 } };

  it("warns on the draft, not when the runner draws arrivals from the mean alone", () => {
    expect(draftArrivalsRunFaster(draft(denser))).not.toBeNull();
    expect(draftArrivalsRunFaster(draft({ ...denser, arrival: { ...denser.arrival, months: [{ month: 12, percent: 40 }] } }))).toBeNull();
  });

  it("leaves the error first when the bounds are not valid", () => {
    expect(draftArrivalsRunFaster(draft({ ...denser, arrival: { ...denser.arrival, maxMinutes: 30 } }))).toBeNull();
  });

  it("keeps monthly rates when the arrivals change", () => {
    const months = [{ month: 12, percent: 40 }];
    const next = withArrival(draft({ ...denser, arrival: { ...denser.arrival, months, bandAttribute: true } }), { meanMinutes: 30, distribution: "expon", maxMinutes: 150 });
    expect(next.arrival).toMatchObject({ months, bandAttribute: true, maxMinutes: 150 });
  });
});
