/**
 * Prosimos-event-log replay engine — a virtual clock over a run's replay
 * artifact. It is the *only* animator of a simulation run (the old
 * `bpmn-js-token-simulation` path is gone), so what you see always matches the
 * numbers.
 *
 * Two clocks (see plan "Architectural rules"):
 *   - ReplayClock   — rAF, ~60fps. Drives the playhead position + token motion.
 *                     Consumed imperatively (`subscribeTick`), never via React
 *                     state, so it never triggers a component render.
 *   - AnalyticsClock — fires only when the bucket index changes (or on
 *                     seek / granularity / focus). Carries the `ReplayFrame`
 *                     that node states, counters and the Cruscotto charts read.
 */
import type { SimulationReplay } from "../simulationTypes";

type ReplayPayload = SimulationReplay["replay"];

export type Granularity = "case" | "sample" | "system";

/** Live queue pressure at a node — NOT a bottleneck verdict (that's full-log). */
export type NodePressure = "none" | "building" | "high" | "saturated";

export type ReplaySpeed = number;

export type SpeedOption = { value: number; label: string };

/**
 * Runs span hours to weeks, so a fixed multiplier list is useless. Derive the
 * options from the run duration as "replay the whole run in ≈ N": a slow one for
 * following a case, up to a fast one that plays the lot in ~12s.
 */
function speedOptionsFor(durationSec: number): SpeedOption[] {
  const targets = [1800, 600, 120, 40, 12]; // wall-clock seconds to replay it all
  return targets.map((wall) => {
    const value = Math.max(1, Math.round(durationSec / wall));
    const label =
      wall >= 60 ? `≈ ${Math.round(wall / 60)} min` : `≈ ${wall} s`;
    return { value, label };
  });
}
const DEFAULT_SPEED_INDEX = 2;

const SAMPLE_TOKEN_CAP = 150;

export type ReplayTokenAt =
  | { kind: "node"; el: string; queued: boolean }
  | { kind: "flow"; from: string; to: string; progress: number };

export type ReplayToken = {
  caseId: string;
  at: ReplayTokenAt;
};

export type ReplayFrame = {
  bucket: number;
  elements: Record<
    string,
    { pressure: NodePressure; active: number; queued: number; done: number }
  >;
  resources: Record<string, { busy: number }>;
  global: {
    activeCases: number;
    queuedCases: number;
    completedCases: number;
    throughputPerHour: number;
    costAccrued: number;
    avgCycleSec: number;
    clockMs: number;
  };
  tokens: ReplayToken[];
};

export type ReplayStatus = {
  playing: boolean;
  speed: ReplaySpeed;
  granularity: Granularity;
  focusCaseId: string | null;
  durationSec: number;
  atEnd: boolean;
};

type TickListener = (tNowSec: number, status: ReplayStatus) => void;
type FrameListener = (frame: ReplayFrame) => void;
type StatusListener = (status: ReplayStatus) => void;

function percentile(sorted: number[], pct: number): number {
  if (sorted.length === 0) return 0;
  if (sorted.length === 1) return sorted[0];
  const rank = (pct / 100) * (sorted.length - 1);
  const lo = Math.floor(rank);
  const hi = Math.ceil(rank);
  return lo === hi
    ? sorted[lo]
    : sorted[lo] + (sorted[hi] - sorted[lo]) * (rank - lo);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Pick a representative case to follow in "case" mode: the median cycle time. */
export function medianCaseId(replay: ReplayPayload): string | null {
  const cases = replay.cases;
  if (cases.length === 0) return null;
  const sorted = [...cases].sort((a, b) => a.cycleSec - b.cycleSec);
  return sorted[Math.floor(sorted.length / 2)]?.id ?? null;
}

export class ReplayEngine {
  private readonly replay: ReplayPayload;
  private readonly startMs_: number;
  private readonly bucketSec: number;
  private readonly lastBucket: number;
  /** per-element queue-history stats, precomputed once */
  private readonly elQueueStats: Record<string, { p75: number; max: number }>;
  private readonly elementIds: string[];
  private readonly resourceIds: string[];

  readonly speedOptions: SpeedOption[];

  private tNow = 0;
  private playing = false;
  private speed: ReplaySpeed;
  private granularity: Granularity = "sample";
  private focusCaseId: string | null;

  private rafId: number | null = null;
  private lastRafMs = 0;
  private emittedBucket = -1;

  private tickListeners = new Set<TickListener>();
  private frameListeners = new Set<FrameListener>();
  private statusListeners = new Set<StatusListener>();

  private statusSnapshot: ReplayStatus;
  private frameSnapshot: ReplayFrame;

  constructor(replay: ReplayPayload) {
    this.replay = replay;
    this.startMs_ = Date.parse(replay.meta.start) || 0;
    this.bucketSec = Math.max(1, replay.meta.bucketSec);
    this.lastBucket = Math.max(0, replay.series.t.length - 1);
    this.focusCaseId = medianCaseId(replay);

    this.speedOptions = speedOptionsFor(replay.meta.durationSec);
    this.speed = this.speedOptions[DEFAULT_SPEED_INDEX].value;

    this.elementIds = Object.keys(replay.series.byElement);
    this.resourceIds = Object.keys(replay.series.byResource);
    this.elQueueStats = {};
    for (const el of this.elementIds) {
      const q = replay.series.byElement[el].queued;
      const sorted = [...q].sort((a, b) => a - b);
      this.elQueueStats[el] = {
        p75: percentile(sorted, 75),
        max: Math.max(1, ...q),
      };
    }

    this.statusSnapshot = this.computeStatus();
    this.frameSnapshot = this.computeFrame();
  }

  // -- lifecycle ---------------------------------------------------------
  destroy(): void {
    this.pause();
    this.tickListeners.clear();
    this.frameListeners.clear();
    this.statusListeners.clear();
  }

  // -- subscriptions (useSyncExternalStore-friendly) --------------------
  subscribeStatus = (cb: StatusListener): (() => void) => {
    this.statusListeners.add(cb);
    return () => this.statusListeners.delete(cb);
  };
  getStatus = (): ReplayStatus => this.statusSnapshot;

  subscribeFrame = (cb: FrameListener): (() => void) => {
    this.frameListeners.add(cb);
    return () => this.frameListeners.delete(cb);
  };
  getFrame = (): ReplayFrame => this.frameSnapshot;

  /** Imperative, ReplayClock-rate. For the token layer + scrubber thumb. */
  subscribeTick = (cb: TickListener): (() => void) => {
    this.tickListeners.add(cb);
    cb(this.tNow, this.statusSnapshot);
    return () => this.tickListeners.delete(cb);
  };

  get durationSec(): number {
    return this.replay.meta.durationSec;
  }
  get startMs(): number {
    return this.startMs_;
  }
  get now(): number {
    return this.tNow;
  }
  get payload(): ReplayPayload {
    return this.replay;
  }

  /** Token positions at the current instant + granularity. Recomputed every
   *  ReplayClock tick by the token layer (flow progress is continuous). */
  tokensAt(): ReplayToken[] {
    return this.computeTokens();
  }

  // -- controls --------------------------------------------------------
  play(): void {
    if (this.playing || this.tNow >= this.durationSec) return;
    this.playing = true;
    this.lastRafMs = performance.now();
    this.commitStatus();
    this.rafId = requestAnimationFrame(this.loop);
  }

  pause(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    if (!this.playing) return;
    this.playing = false;
    this.commitStatus();
  }

  toggle(): void {
    if (this.playing) this.pause();
    else this.play();
  }

  seek(tSec: number): void {
    this.tNow = clamp(tSec, 0, this.durationSec);
    this.emitTick();
    this.maybeCommitFrame(true);
    this.commitStatus();
  }

  setSpeed(speed: ReplaySpeed): void {
    this.speed = speed;
    this.commitStatus();
  }

  setGranularity(granularity: Granularity): void {
    if (granularity === this.granularity) return;
    this.granularity = granularity;
    this.maybeCommitFrame(true);
    this.emitTick();
    this.commitStatus();
  }

  setFocusCase(caseId: string | null): void {
    this.focusCaseId = caseId;
    if (this.granularity === "case") {
      this.maybeCommitFrame(true);
      this.emitTick();
    }
    this.commitStatus();
  }

  restart(): void {
    this.seek(0);
  }

  // -- loop ----------------------------------------------------------
  private loop = (nowMs: number): void => {
    if (!this.playing) return;
    const dtWall = (nowMs - this.lastRafMs) / 1000;
    this.lastRafMs = nowMs;
    this.tNow = Math.min(this.durationSec, this.tNow + dtWall * this.speed);

    this.emitTick();
    this.maybeCommitFrame(false);

    if (this.tNow >= this.durationSec) {
      this.pause();
      return;
    }
    this.rafId = requestAnimationFrame(this.loop);
  };

  private emitTick(): void {
    for (const cb of this.tickListeners) cb(this.tNow, this.statusSnapshot);
  }

  private currentBucket(): number {
    return clamp(Math.floor(this.tNow / this.bucketSec), 0, this.lastBucket);
  }

  private maybeCommitFrame(force: boolean): void {
    const bucket = this.currentBucket();
    if (!force && bucket === this.emittedBucket) return;
    this.emittedBucket = bucket;
    this.frameSnapshot = this.computeFrame();
    for (const cb of this.frameListeners) cb(this.frameSnapshot);
  }

  private commitStatus(): void {
    this.statusSnapshot = this.computeStatus();
    for (const cb of this.statusListeners) cb(this.statusSnapshot);
  }

  private computeStatus(): ReplayStatus {
    return {
      playing: this.playing,
      speed: this.speed,
      granularity: this.granularity,
      focusCaseId: this.focusCaseId,
      durationSec: this.durationSec,
      atEnd: this.tNow >= this.durationSec,
    };
  }

  // -- frame derivation --------------------------------------------
  private computeFrame(): ReplayFrame {
    const bucket = this.currentBucket();
    const s = this.replay.series;

    const elements: ReplayFrame["elements"] = {};
    for (const el of this.elementIds) {
      const col = s.byElement[el];
      const queued = col.queued[bucket] ?? 0;
      const active = col.active[bucket] ?? 0;
      const prevQueued = bucket > 0 ? col.queued[bucket - 1] ?? 0 : 0;
      elements[el] = {
        active,
        queued,
        done: col.done[bucket] ?? 0,
        pressure: this.pressure(el, queued, active, queued > prevQueued),
      };
    }

    const resources: ReplayFrame["resources"] = {};
    for (const r of this.resourceIds) {
      resources[r] = { busy: s.byResource[r].busy[bucket] ?? 0 };
    }

    const g = s.global;
    const at = (arr: number[] | undefined) => (arr ? arr[bucket] ?? 0 : 0);

    return {
      bucket,
      elements,
      resources,
      global: {
        activeCases: at(g.wip),
        queuedCases: at(g.queued),
        completedCases: at(g.done),
        throughputPerHour: at(g.throughputPerHour),
        costAccrued: at(g.costAccrued),
        avgCycleSec: at(g.avgCycleSec),
        clockMs: this.startMs_ + this.tNow * 1000,
      },
      tokens: this.computeTokens(),
    };
  }

  private pressure(
    el: string,
    queued: number,
    active: number,
    rising: boolean,
  ): NodePressure {
    if (queued <= 0) return "none";
    const stats = this.elQueueStats[el];
    if (queued >= Math.max(3, stats.max * 0.8)) return "saturated";
    if (queued >= Math.max(2, stats.p75) && queued > active) return "high";
    return rising || queued >= 1 ? "building" : "none";
  }

  private computeTokens(): ReplayToken[] {
    if (this.granularity === "system") return [];

    const t = this.tNow;
    const cases =
      this.granularity === "case"
        ? this.replay.cases.filter((c) => c.id === this.focusCaseId)
        : this.replay.cases;

    const out: ReplayToken[] = [];
    for (const c of cases) {
      const token = tokenForCase(c.events, t);
      if (token) out.push({ caseId: c.id, at: token });
      if (this.granularity === "sample" && out.length >= SAMPLE_TOKEN_CAP) break;
    }
    return out;
  }
}

type CaseEvent = ReplayPayload["cases"][number]["events"][number];

function tokenForCase(events: CaseEvent[], t: number): ReplayTokenAt | null {
  if (events.length === 0) return null;
  if (t < events[0].enable) return null;
  const last = events[events.length - 1];
  if (t >= last.end) return null;

  for (let i = 0; i < events.length; i += 1) {
    const e = events[i];
    if (t >= e.enable && t < e.start && e.el) {
      return { kind: "node", el: e.el, queued: true };
    }
    if (t >= e.start && t < e.end && e.el) {
      return { kind: "node", el: e.el, queued: false };
    }
    // in transit between this event's end and the next event's enable
    const next = events[i + 1];
    if (next && t >= e.end && t < next.enable) {
      if (e.el && next.el) {
        const span = Math.max(1e-6, next.enable - e.end);
        return {
          kind: "flow",
          from: e.el,
          to: next.el,
          progress: clamp((t - e.end) / span, 0, 1),
        };
      }
      return e.el
        ? { kind: "node", el: e.el, queued: false }
        : next.el
          ? { kind: "node", el: next.el, queued: true }
          : null;
    }
  }
  return null;
}
