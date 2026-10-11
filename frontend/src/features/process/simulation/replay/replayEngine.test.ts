import { describe, expect, it } from "vitest";

import { ReplayEngine, medianCaseId, pickCaseId, tokenForCase } from "./replayEngine";
import type { SimulationReplay } from "../simulationTypes";

type Payload = SimulationReplay["replay"];

/** 4 buckets (5 points), bucketSec 100, duration 400. Two activities A, B. */
function makePayload(): Payload {
  return {
    schemaVersion: 1,
    meta: {
      start: "2026-01-05T09:00:00+00:00",
      durationSec: 400,
      totalCases: 3,
      sampledCases: 3,
      bucketSec: 100,
    },
    elements: { A: { name: "Alpha" }, B: { name: "Beta" } },
    cases: [
      {
        id: "0",
        cycleSec: 150,
        events: [
          { el: "A", enable: 0, start: 0, end: 50, res: "r" },
          { el: "B", enable: 50, start: 100, end: 150, res: "r" },
        ],
      },
      {
        id: "1",
        cycleSec: 250,
        events: [
          { el: "A", enable: 0, start: 50, end: 120, res: "r" },
          { el: "B", enable: 120, start: 200, end: 250, res: "r" },
        ],
      },
      {
        id: "2",
        cycleSec: 400,
        events: [{ el: "A", enable: 0, start: 200, end: 400, res: "r" }],
      },
    ],
    series: {
      t: [0, 100, 200, 300, 400],
      byElement: {
        A: { active: [2, 1, 1, 0, 0], queued: [1, 0, 0, 0, 0], done: [0, 1, 1, 2, 3] },
        B: { active: [0, 1, 1, 0, 0], queued: [0, 1, 0, 0, 0], done: [0, 0, 1, 2, 2] },
      },
      byResource: { r: { busy: [1, 1, 0.5, 0, 0] } },
      global: {
        wip: [3, 2, 2, 1, 0],
        queued: [1, 1, 0, 0, 0],
        done: [0, 1, 1, 2, 3],
        throughputPerHour: [0, 36, 0, 36, 36],
        costAccrued: [0, 10, 20, 30, 40],
        avgCycleSec: [0, 150, 150, 200, 267],
      },
    },
    flows: { flowAB: { count: 3, attributed: true } },
  };
}

describe("ReplayEngine", () => {
  it("keeps short-run speeds distinct and describes the actual replay duration", () => {
    const engine = new ReplayEngine(makePayload());
    expect(engine.speedOptions.map((option) => option.value)).toEqual([1, 3, 10, 33]);
    expect(engine.speedOptions[0].label).toBe("≈ 7 min");
    expect(engine.getStatus().speed).toBe(3);
  });
  it("picks the median-cycle case to follow", () => {
    expect(medianCaseId(makePayload())).toBe("1");
  });

  it("derives the frame at the bucket containing tNow", () => {
    const engine = new ReplayEngine(makePayload());
    engine.seek(0);
    let frame = engine.getFrame();
    expect(frame.bucket).toBe(0);
    expect(frame.elements.A.active).toBe(2);
    expect(frame.elements.A.queued).toBe(1);
    expect(frame.global.completedCases).toBe(0);

    engine.seek(250);
    frame = engine.getFrame();
    expect(frame.bucket).toBe(2);
    expect(frame.global.activeCases).toBe(2);
    expect(frame.global.costAccrued).toBe(20);

    engine.seek(400);
    frame = engine.getFrame();
    expect(frame.bucket).toBe(4);
    expect(frame.global.completedCases).toBe(3);
    expect(frame.global.activeCases).toBe(0);
  });

  it("clamps seek to the run bounds and reports atEnd", () => {
    const engine = new ReplayEngine(makePayload());
    engine.seek(99999);
    expect(engine.now).toBe(400);
    expect(engine.getStatus().atEnd).toBe(true);
    engine.seek(-100);
    expect(engine.now).toBe(0);
  });

  it("advances the simulation clock relative to meta.start", () => {
    const engine = new ReplayEngine(makePayload());
    engine.seek(200);
    const clock = engine.getFrame().global.clockMs;
    expect(clock).toBe(Date.parse("2026-01-05T09:00:00+00:00") + 200_000);
  });

  it("emits a fresh frame reference only when the bucket changes", () => {
    const engine = new ReplayEngine(makePayload());
    const frames: number[] = [];
    engine.subscribeFrame((f) => frames.push(f.bucket));
    engine.seek(10); // bucket 0 (forced on seek)
    engine.seek(150); // bucket 1
    engine.seek(160); // still bucket 1 -> forced emit on seek
    expect(frames).toEqual([0, 1, 1]);
  });

  describe("tokens", () => {
    it("case mode follows exactly one token along the focused case", () => {
      const engine = new ReplayEngine(makePayload());
      engine.setGranularity("case");
      engine.setFocusCase("1");

      engine.seek(30); // case 1: enabled at A, not started (start 50) -> queued at A
      expect(engine.tokensAt()).toEqual([
        { caseId: "1", at: { kind: "node", el: "A", queued: true } },
      ]);

      engine.seek(80); // in A (start 50, end 120)
      expect(engine.tokensAt()[0].at).toEqual({ kind: "node", el: "A", queued: false });

      engine.seek(300); // after last end (250) -> no token
      expect(engine.tokensAt()).toEqual([]);
    });

    it("sample mode shows a token per in-flight case, none in system mode", () => {
      const engine = new ReplayEngine(makePayload());
      engine.seek(60);
      engine.setGranularity("sample");
      expect(engine.tokensAt().length).toBeGreaterThan(0);

      engine.setGranularity("system");
      expect(engine.tokensAt()).toEqual([]);
    });

    it("places a token on the connecting flow between two activities", () => {
      // speed 3 (400s / 120) -> a hop lasts 0.7 * 3 = 2.1 sim seconds
      const engine = new ReplayEngine(makePayload());
      engine.setGranularity("case");
      engine.setFocusCase("1"); // A ends 120, B enables 120: no gap in sim time
      engine.seek(121);
      const at = engine.tokensAt()[0].at;
      expect(at).toMatchObject({ kind: "flow", from: "A", to: "B" });
      expect(at.kind === "flow" && at.progress).toBeCloseTo(1 / 2.1, 5);

      engine.seek(123); // hop over: queued at B (start 200)
      expect(engine.tokensAt()[0].at).toEqual({ kind: "node", el: "B", queued: true });
    });
  });

  describe("token travel", () => {
    const events = [
      { el: "A", enable: 0, start: 0, end: 50, res: "r" },
      { el: "B", enable: 50, start: 100, end: 150, res: "r" },
    ];

    it("without travel the case jumps from step to step (sim time only)", () => {
      expect(tokenForCase(events, 0)).toEqual({ kind: "node", el: "A", queued: false });
      expect(tokenForCase(events, 50)).toEqual({ kind: "node", el: "B", queued: true });
      expect(tokenForCase(events, 150)).toBeNull();
    });

    it("is born at the start event, hops between steps and leaves at the end", () => {
      expect(tokenForCase(events, 5, 10)).toEqual({ kind: "flow", from: null, to: "A", progress: 0.5 });
      expect(tokenForCase(events, 12, 10)).toEqual({ kind: "node", el: "A", queued: false });
      expect(tokenForCase(events, 55, 10)).toEqual({ kind: "flow", from: "A", to: "B", progress: 0.5 });
      expect(tokenForCase(events, 70, 10)).toEqual({ kind: "node", el: "B", queued: true });
      expect(tokenForCase(events, 155, 10)).toEqual({ kind: "flow", from: "B", to: null, progress: 0.5 });
      expect(tokenForCase(events, 160, 10)).toBeNull();
    });

    it("never takes more than half of a short step", () => {
      const quick = [
        { el: "A", enable: 0, start: 0, end: 4, res: "r" },
        { el: "B", enable: 4, start: 4, end: 8, res: "r" },
      ];
      expect(tokenForCase(quick, 1, 100)).toMatchObject({ kind: "flow", to: "A", progress: 0.5 });
      expect(tokenForCase(quick, 3, 100)).toEqual({ kind: "node", el: "A", queued: false });
      expect(tokenForCase(quick, 7, 100)).toEqual({ kind: "node", el: "B", queued: false });
    });

    it("uses the real gap when it is longer than the hop", () => {
      const gap = [
        { el: "A", enable: 0, start: 0, end: 10, res: "r" },
        { el: "B", enable: 50, start: 50, end: 100, res: "r" },
      ];
      expect(tokenForCase(gap, 30, 2)).toEqual({ kind: "flow", from: "A", to: "B", progress: 0.5 });
    });
  });

  describe("case depth (phase 7)", () => {
    it("picks the fastest / slowest case by cycle time", () => {
      const p = makePayload();
      expect(pickCaseId(p, "fastest")).toBe("0"); // 150s
      expect(pickCaseId(p, "slowest")).toBe("2"); // 400s
      expect(pickCaseId(p, "median")).toBe("1");
    });

    it("followCase switches to case mode and seeks onto the case", () => {
      const engine = new ReplayEngine(makePayload());
      engine.seek(390); // past case 0's life (ends 150)
      engine.followCase("fastest");
      expect(engine.getStatus().granularity).toBe("case");
      expect(engine.getStatus().focusCaseId).toBe("0");
      expect(engine.now).toBe(0); // case 0 starts at enable 0
      expect(engine.tokensAt()).toHaveLength(1);
    });

    it("followCase keeps the clock when it is already inside the case", () => {
      const engine = new ReplayEngine(makePayload());
      engine.seek(100);
      engine.followCase("slowest"); // case 2 spans 0..400
      expect(engine.now).toBe(100);
    });

    it("exposes the focused case timeline and its serving pool", () => {
      const engine = new ReplayEngine(makePayload());
      engine.followCase("median"); // case 1
      const rows = engine.focusCaseEvents();
      expect(rows?.map((r) => r.name)).toEqual(["Alpha", "Beta"]);
      expect(rows?.[0]).toMatchObject({ enable: 0, start: 50, end: 120, res: "r" });
      expect(engine.focusCaseSpan()).toMatchObject({ start: 0, end: 250, cycleSec: 250 });
      expect(engine.poolForElement("A")).toBe("r");
      expect(engine.poolForElement("nope")).toBeNull();
    });
  });

  it("escalates node pressure with queue depth", () => {
    const payload = makePayload();
    payload.series.byElement.A.queued = [1, 3, 8, 0, 0];
    payload.series.byElement.A.active = [1, 1, 1, 0, 0];
    const engine = new ReplayEngine(payload);

    engine.seek(0);
    expect(engine.getFrame().elements.A.pressure).toBe("building"); // q 1
    engine.seek(100);
    expect(engine.getFrame().elements.A.pressure).toBe("high"); // q 3, rising, > active
    engine.seek(200);
    expect(engine.getFrame().elements.A.pressure).toBe("saturated"); // q 8 ~= max
    engine.seek(300);
    expect(engine.getFrame().elements.A.pressure).toBe("none"); // q 0
  });
});
