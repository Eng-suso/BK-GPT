/**
 * Turn two run summaries into a KPI delta table + per-element wait deltas for the
 * Compare screen. Reads only what the backend already computed (Phase 1
 * `_build_summary`) — never recomputes a metric from sampled data.
 */
import type { SimulationSummary } from "./simulationTypes";

export type DeltaDirection = "better" | "worse" | "same";
export type DeltaFormat = "duration" | "currency" | "rate" | "percent" | "count";

export type KpiDelta = {
  key: string;
  /** i18n key under simulation.compare.kpi.* */
  labelKey: string;
  a: number;
  b: number;
  delta: number;
  deltaPct: number | null;
  betterIs: "lower" | "higher";
  direction: DeltaDirection;
  format: DeltaFormat;
};

export type ElementDelta = {
  el: string;
  name: string;
  aWait: number;
  bWait: number;
  deltaWait: number;
  direction: DeltaDirection;
};

const SAME_EPS = 0.02; // <2% change reads as "no material difference"

function num(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function get(summary: SimulationSummary | null | undefined, path: string[]): number {
  let cur: unknown = summary;
  for (const key of path) {
    if (cur && typeof cur === "object") cur = (cur as Record<string, unknown>)[key];
    else return 0;
  }
  return num(cur);
}

function busiestUtilisation(summary: SimulationSummary | null | undefined): number {
  const rows = (summary?.byResource as Array<Record<string, unknown>> | undefined) ?? [];
  return rows.reduce((max, r) => Math.max(max, num(r.utilizationPct)), 0);
}

function direction(delta: number, base: number, betterIs: "lower" | "higher"): DeltaDirection {
  if (base > 0 && Math.abs(delta) / base < SAME_EPS) return "same";
  if (delta === 0) return "same";
  const bWins = betterIs === "lower" ? delta < 0 : delta > 0;
  return bWins ? "better" : "worse";
}

const KPI_SPECS: Array<{
  key: string;
  labelKey: string;
  pick: (s: SimulationSummary | null | undefined) => number;
  betterIs: "lower" | "higher";
  format: DeltaFormat;
}> = [
  { key: "cycleAvg", labelKey: "cycleAvg", pick: (s) => get(s, ["cycle", "avg"]), betterIs: "lower", format: "duration" },
  { key: "cycleP95", labelKey: "cycleP95", pick: (s) => get(s, ["cycle", "p95"]), betterIs: "lower", format: "duration" },
  { key: "waitAvg", labelKey: "waitAvg", pick: (s) => get(s, ["waiting", "avg"]), betterIs: "lower", format: "duration" },
  { key: "costPerCase", labelKey: "costPerCase", pick: (s) => get(s, ["cost", "perCase"]), betterIs: "lower", format: "currency" },
  { key: "throughput", labelKey: "throughput", pick: (s) => get(s, ["throughputPerHour"]), betterIs: "higher", format: "rate" },
  { key: "busiestResource", labelKey: "busiestResource", pick: busiestUtilisation, betterIs: "lower", format: "percent" },
];

export function kpiDeltas(
  a: SimulationSummary | null | undefined,
  b: SimulationSummary | null | undefined,
): KpiDelta[] {
  return KPI_SPECS.map((spec) => {
    const av = spec.pick(a);
    const bv = spec.pick(b);
    const delta = bv - av;
    return {
      key: spec.key,
      labelKey: spec.labelKey,
      a: av,
      b: bv,
      delta,
      deltaPct: av !== 0 ? delta / av : null,
      betterIs: spec.betterIs,
      direction: direction(delta, av, spec.betterIs),
      format: spec.format,
    };
  });
}

export function elementWaitDeltas(
  a: SimulationSummary | null | undefined,
  b: SimulationSummary | null | undefined,
): ElementDelta[] {
  const rowsA = (a?.byActivity as Array<Record<string, unknown>> | undefined) ?? [];
  const rowsB = (b?.byActivity as Array<Record<string, unknown>> | undefined) ?? [];
  const byElA = new Map(rowsA.filter((r) => r.el).map((r) => [String(r.el), r]));
  const byElB = new Map(rowsB.filter((r) => r.el).map((r) => [String(r.el), r]));

  const out: ElementDelta[] = [];
  for (const el of new Set([...byElA.keys(), ...byElB.keys()])) {
    const ra = byElA.get(el);
    const rb = byElB.get(el);
    const aWait = num((ra?.wait as Record<string, unknown>)?.avg);
    const bWait = num((rb?.wait as Record<string, unknown>)?.avg);
    const deltaWait = bWait - aWait;
    out.push({
      el,
      name: String(rb?.name ?? ra?.name ?? el),
      aWait,
      bWait,
      deltaWait,
      direction: direction(deltaWait, aWait || bWait, "lower"),
    });
  }
  return out.sort((x, y) => Math.abs(y.deltaWait) - Math.abs(x.deltaWait));
}
