import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-04: le ripetizioni di uno scenario e l'intervallo di ogni KPI.
 *
 * Intervallo al 95% della media con la t di Student (n - 1 gradi di liberta'):
 * con poche ripetizioni e' piu' largo della normale, e deve esserlo.
 */

/** t al 97,5% per 1..19 gradi di liberta' (fino a 20 ripetizioni). */
const T_975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131, 2.12, 2.11, 2.101, 2.093];

export type Interval = { mean: number; half: number; n: number };

export function interval(values: number[]): Interval | null {
  const n = values.length;
  if (n < 2) return null;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / (n - 1);
  const t = T_975[Math.min(n - 1, T_975.length) - 1];
  return { mean, half: (t * Math.sqrt(variance)) / Math.sqrt(n), n };
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

/** I KPI di ogni ripetizione completata, con il loro intervallo. */
export function replicationIntervals(members: SimulationRun[]): Record<ReplicationKpi, Interval | null> {
  const done = members.filter((r) => r.status === "completed" && r.summary);
  const pick = (f: (r: SimulationRun) => number | undefined) =>
    interval(done.map(f).filter((v): v is number => typeof v === "number" && Number.isFinite(v)));
  return {
    cycle: pick((r) => r.summary?.cycle.avg),
    waiting: pick((r) => r.summary?.waiting.avg),
    costPerCase: pick((r) => r.summary?.cost.perCase),
    throughput: pick((r) => r.summary?.throughputPerHour),
  };
}
