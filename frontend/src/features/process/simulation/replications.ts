import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-04: le ripetizioni di uno scenario e l'intervallo di ogni KPI.
 *
 * Intervallo al 95% della media con la t di Student (n - 1 gradi di liberta'):
 * con poche ripetizioni e' piu' largo della normale, e deve esserlo.
 */

/**
 * t al 97,5% per 1..40 gradi di liberta': 19 bastano per una ripetizione, il
 * confronto fra due gruppi (Welch) arriva a 38. Oltre, l'ultimo valore: piu'
 * prudente della normale.
 */
const T_975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131, 2.12, 2.11, 2.101, 2.093,
  2.086, 2.08, 2.074, 2.069, 2.064, 2.06, 2.056, 2.052, 2.048, 2.045, 2.042, 2.04, 2.037, 2.035, 2.032, 2.03, 2.028, 2.026, 2.024, 2.023, 2.021];

/** Gradi di liberta' non interi (Welch): si arrotonda per difetto, cioe' verso l'intervallo piu' largo. */
function t975(df: number): number {
  return T_975[Math.min(Math.max(1, Math.floor(df)), T_975.length) - 1];
}

function meanAndVariance(values: number[]): { mean: number; variance: number } {
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  return { mean, variance: values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / (n - 1) };
}

export type Interval = { mean: number; half: number; n: number };

export function interval(values: number[]): Interval | null {
  const n = values.length;
  if (n < 2) return null;
  const { mean, variance } = meanAndVariance(values);
  return { mean, half: (t975(n - 1) * Math.sqrt(variance)) / Math.sqrt(n), n };
}

export function replicationGroup(run: SimulationRun | null | undefined): string | null {
  const group = run?.request?.replication_group;
  return typeof group === "string" && group ? group : null;
}

/** Le ripetizioni del gruppo del run, in ordine. */
export function groupMembers(run: SimulationRun | null | undefined, runs: SimulationRun[]): SimulationRun[] {
  const group = replicationGroup(run);
  if (!group) return [];
  const index = (r: SimulationRun) => Number(r.request?.replication_index ?? 0);
  return runs.filter((r) => replicationGroup(r) === group).sort((a, b) => index(a) - index(b));
}

export type ReplicationKpi = "cycle" | "waiting" | "costPerCase" | "throughput";

const KPI_VALUE: Record<ReplicationKpi, (r: SimulationRun) => number | undefined> = {
  cycle: (r) => r.summary?.cycle.avg,
  waiting: (r) => r.summary?.waiting.avg,
  costPerCase: (r) => r.summary?.cost.perCase,
  throughput: (r) => r.summary?.throughputPerHour,
};

/** Per ogni KPI, se il valore migliore e' il piu' basso o il piu' alto. */
export const KPI_BETTER: Record<ReplicationKpi, "lower" | "higher"> = {
  cycle: "lower", waiting: "lower", costPerCase: "lower", throughput: "higher",
};

const finite = (v: number | undefined): v is number => typeof v === "number" && Number.isFinite(v);
const completed = (members: SimulationRun[]) => members.filter((r) => r.status === "completed" && r.summary);

/** I KPI di ogni ripetizione completata, con il loro intervallo. */
export function replicationIntervals(members: SimulationRun[]): Record<ReplicationKpi, Interval | null> {
  const done = completed(members);
  const pick = (kpi: ReplicationKpi) => interval(done.map(KPI_VALUE[kpi]).filter(finite));
  return { cycle: pick("cycle"), waiting: pick("waiting"), costPerCase: pick("costPerCase"), throughput: pick("throughput") };
}

/**
 * SIM-04, seconda parte: la differenza B - A fra due scenari ripetuti, con il
 * suo intervallo al 95%. "B migliore" solo se l'intervallo non comprende zero:
 * altrimenti la differenza potrebbe essere il caso.
 */
export type DeltaVerdict = "better" | "worse" | "unclear";
export type DeltaInterval = { a: number; b: number; delta: number; half: number; verdict: DeltaVerdict };
export type GroupComparison = {
  /** Ripetizioni con lo stesso seed nei due scenari: si confrontano a coppie. */
  paired: boolean;
  nA: number;
  nB: number;
  kpis: Record<ReplicationKpi, DeltaInterval | null>;
};

export function deltaInterval(a: number[], b: number[], betterIs: "lower" | "higher", paired: boolean): DeltaInterval | null {
  if (a.length < 2 || b.length < 2 || (paired && a.length !== b.length)) return null;
  const ma = meanAndVariance(a);
  const mb = meanAndVariance(b);
  const delta = mb.mean - ma.mean;
  let half: number;
  if (paired) {
    const diff = meanAndVariance(b.map((v, i) => v - a[i]));
    half = (t975(a.length - 1) * Math.sqrt(diff.variance)) / Math.sqrt(a.length);
  } else {
    const va = ma.variance / a.length;
    const vb = mb.variance / b.length;
    const se = Math.sqrt(va + vb);
    const df = se === 0 ? a.length + b.length - 2 : (va + vb) ** 2 / (va ** 2 / (a.length - 1) + vb ** 2 / (b.length - 1));
    half = t975(df) * se;
  }
  const decided = delta !== 0 && Math.abs(delta) > half;
  const bWins = betterIs === "lower" ? delta < 0 : delta > 0;
  return { a: ma.mean, b: mb.mean, delta, half, verdict: decided ? (bWins ? "better" : "worse") : "unclear" };
}

/** Il confronto fra i gruppi di due run, o null se uno dei due non ha almeno due ripetizioni completate. */
export function compareGroups(runA: SimulationRun, runB: SimulationRun, runs: SimulationRun[]): GroupComparison | null {
  const groupA = completed(groupMembers(runA, runs));
  const groupB = completed(groupMembers(runB, runs));
  if (groupA.length < 2 || groupB.length < 2 || replicationGroup(runA) === replicationGroup(runB)) return null;
  const seed = (r: SimulationRun) => r.request?.seed;
  const index = (r: SimulationRun) => Number(r.request?.replication_index ?? 0);
  const byIndex = new Map(groupB.map((r) => [index(r), r]));
  const pairs = groupA.flatMap((r) => {
    const other = byIndex.get(index(r));
    return other && seed(other) !== undefined && seed(other) === seed(r) ? [[r, other] as const] : [];
  });
  const paired = pairs.length >= 2 && pairs.length === groupA.length && pairs.length === groupB.length;
  const kpi = (name: ReplicationKpi): DeltaInterval | null => {
    if (paired) {
      const rows = pairs.map(([x, y]) => [KPI_VALUE[name](x), KPI_VALUE[name](y)] as const).filter(([x, y]) => finite(x) && finite(y));
      return deltaInterval(rows.map(([x]) => x as number), rows.map(([, y]) => y as number), KPI_BETTER[name], true);
    }
    return deltaInterval(groupA.map(KPI_VALUE[name]).filter(finite), groupB.map(KPI_VALUE[name]).filter(finite), KPI_BETTER[name], false);
  };
  return {
    paired,
    nA: groupA.length,
    nB: groupB.length,
    kpis: { cycle: kpi("cycle"), waiting: kpi("waiting"), costPerCase: kpi("costPerCase"), throughput: kpi("throughput") },
  };
}
