import { scenarioValue, type ScenarioDelta, type ScenarioRuns } from "./scenarioWorkspace";
import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-24: la lettura di un'alternativa contro l'AS-IS, calcolata.
 *
 * Due cose che il consulente altrimenti ricava dalle tabelle: dove si sposta il
 * vincolo (il collo di bottiglia diagnosticato nei due run) e che scambio c'e'
 * fra tempo e costo. Tutto viene dai run; una differenza che l'intervallo non
 * distingue da zero non si racconta come un guadagno.
 */

type Bottleneck = { el: string | null; name: string };

/** Il collo di bottiglia piu' frequente fra i run completati (con le ripetizioni puo' cambiare). */
export function dominantBottleneck(runs: SimulationRun[]): Bottleneck | null {
  const counts = new Map<string, { item: Bottleneck; n: number }>();
  for (const run of runs) {
    const raw = run.summary?.bottleneck as { el?: unknown; name?: unknown } | null | undefined;
    if (!raw || typeof raw.name !== "string") continue;
    const item = { el: typeof raw.el === "string" ? raw.el : null, name: raw.name };
    const key = item.el ?? item.name;
    const entry = counts.get(key) ?? { item, n: 0 };
    entry.n += 1;
    counts.set(key, entry);
  }
  let best: { item: Bottleneck; n: number } | null = null;
  for (const entry of counts.values()) if (!best || entry.n > best.n) best = entry;
  return best?.item ?? null;
}

function waitAt(runs: SimulationRun[], el: string | null, name: string): number | null {
  const values = runs.flatMap((run) => {
    const rows = (run.summary?.byActivity ?? []) as { el?: unknown; name?: unknown; wait?: { avg?: unknown } }[];
    const row = rows.find((r) => (el ? r.el === el : r.name === name));
    const avg = row?.wait?.avg;
    return typeof avg === "number" && Number.isFinite(avg) ? [avg] : [];
  });
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export type ConstraintShift =
  | { kind: "none" }
  | { kind: "same"; at: Bottleneck; waitBefore: number | null; waitAfter: number | null }
  | { kind: "moved"; from: Bottleneck; to: Bottleneck; waitBefore: number | null; waitAfter: number | null }
  | { kind: "relieved"; from: Bottleneck; waitBefore: number | null; waitAfter: number | null }
  | { kind: "appeared"; to: Bottleneck };

export type TradeOff =
  | { kind: "unknown" }
  | { kind: "unclear" }
  /** Cambia solo il tempo o solo il costo; l'altro non si distingue da zero. */
  | { kind: "onlyCycle"; cycle: number }
  | { kind: "onlyCost"; cost: number }
  | { kind: "better"; cycle: number; cost: number }
  | { kind: "worse"; cycle: number; cost: number }
  /** Piu' veloce ma piu' caro: quanto costa ogni ora risparmiata per caso. */
  | { kind: "faster"; cycle: number; cost: number; perHour: number }
  /** Meno caro ma piu' lento: quanto si risparmia per ogni ora in piu' per caso. */
  | { kind: "cheaper"; cycle: number; cost: number; perHour: number };

export type Interpretation = { constraint: ConstraintShift; tradeOff: TradeOff };

/** Una differenza che si puo' raccontare: con l'intervallo, solo se esclude lo zero. */
function certain(delta: ScenarioDelta | null): number | null {
  if (!delta) return null;
  if (delta.kind === "single") return delta.delta;
  return delta.value.verdict === "better" || delta.value.verdict === "worse" ? delta.value.delta : 0;
}

export function interpret(
  asIs: ScenarioRuns,
  alternative: ScenarioRuns,
  deltas: { kpis: { cycle: ScenarioDelta | null; costPerCase: ScenarioDelta | null }; mismatch: boolean },
): Interpretation {
  const before = dominantBottleneck(asIs.completed);
  const after = dominantBottleneck(alternative.completed);
  const same = (a: Bottleneck, b: Bottleneck) => (a.el && b.el ? a.el === b.el : a.name === b.name);
  let constraint: ConstraintShift = { kind: "none" };
  if (before && after) {
    constraint = same(before, after)
      ? { kind: "same", at: before, waitBefore: waitAt(asIs.completed, before.el, before.name), waitAfter: waitAt(alternative.completed, before.el, before.name) }
      : { kind: "moved", from: before, to: after, waitBefore: waitAt(asIs.completed, before.el, before.name), waitAfter: waitAt(alternative.completed, before.el, before.name) };
  } else if (before) {
    constraint = { kind: "relieved", from: before, waitBefore: waitAt(asIs.completed, before.el, before.name), waitAfter: waitAt(alternative.completed, before.el, before.name) };
  } else if (after) {
    constraint = { kind: "appeared", to: after };
  }

  if (deltas.mismatch || !scenarioValue(asIs, "cycle") || !scenarioValue(alternative, "cycle")) {
    return { constraint, tradeOff: { kind: "unknown" } };
  }
  const cycle = certain(deltas.kpis.cycle);
  const cost = certain(deltas.kpis.costPerCase);
  if (cycle === null || cost === null) return { constraint, tradeOff: { kind: "unknown" } };
  if (cycle === 0 && cost === 0) return { constraint, tradeOff: { kind: "unclear" } };
  if (cost === 0) return { constraint, tradeOff: { kind: "onlyCycle", cycle } };
  if (cycle === 0) return { constraint, tradeOff: { kind: "onlyCost", cost } };
  const hours = Math.abs(cycle) / 3600;
  if (cycle <= 0 && cost <= 0) return { constraint, tradeOff: { kind: "better", cycle, cost } };
  if (cycle >= 0 && cost >= 0) return { constraint, tradeOff: { kind: "worse", cycle, cost } };
  if (cycle < 0) return { constraint, tradeOff: { kind: "faster", cycle, cost, perHour: cost / hours } };
  return { constraint, tradeOff: { kind: "cheaper", cycle, cost, perHour: -cost / hours } };
}

type T = (key: string, options?: Record<string, unknown>) => string;

/** La lettura in frasi, nella lingua del consulente. */
export function interpretationLines(
  value: Interpretation,
  t: T,
  format: { duration: (seconds: number) => string; currency: (value: number) => string },
): string[] {
  const k = (key: string, options?: Record<string, unknown>) => t(`simulation.interpretation.${key}`, options);
  const wait = (before: number | null, after: number | null) =>
    before !== null && after !== null ? ` ${k("wait", { before: format.duration(before), after: format.duration(after) })}` : "";
  const lines: string[] = [];
  const c = value.constraint;
  if (c.kind === "same") lines.push(k("same", { name: c.at.name }) + wait(c.waitBefore, c.waitAfter));
  if (c.kind === "moved") lines.push(k("moved", { from: c.from.name, to: c.to.name }) + wait(c.waitBefore, c.waitAfter));
  if (c.kind === "relieved") lines.push(k("relieved", { name: c.from.name }) + wait(c.waitBefore, c.waitAfter));
  if (c.kind === "appeared") lines.push(k("appeared", { name: c.to.name }));
  const o = value.tradeOff;
  const abs = (v: number) => Math.abs(v);
  if (o.kind === "unclear") lines.push(k("unclear"));
  if (o.kind === "onlyCycle") lines.push(k(o.cycle < 0 ? "onlyFaster" : "onlySlower", { cycle: format.duration(abs(o.cycle)) }));
  if (o.kind === "onlyCost") lines.push(k(o.cost < 0 ? "onlyCheaper" : "onlyCostlier", { cost: format.currency(abs(o.cost)) }));
  if (o.kind === "better") lines.push(k("better", { cycle: format.duration(abs(o.cycle)), cost: format.currency(abs(o.cost)) }));
  if (o.kind === "worse") lines.push(k("worse", { cycle: format.duration(abs(o.cycle)), cost: format.currency(abs(o.cost)) }));
  if (o.kind === "faster") lines.push(k("faster", { cycle: format.duration(abs(o.cycle)), cost: format.currency(abs(o.cost)), perHour: format.currency(abs(o.perHour)) }));
  if (o.kind === "cheaper") lines.push(k("cheaper", { cycle: format.duration(abs(o.cycle)), cost: format.currency(abs(o.cost)), perHour: format.currency(abs(o.perHour)) }));
  return lines;
}
