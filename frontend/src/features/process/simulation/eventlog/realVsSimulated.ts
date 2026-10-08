/**
 * Reale contro simulato (B2): i KPI del log reale accanto a quelli di un run,
 * per l'intero processo e per attivita'. Entrambi i lati vengono dallo stesso
 * calcolo del backend (`summarize_log_events`), quindi qui si confronta e basta:
 * nessun KPI viene ricalcolato.
 *
 * Lo scarto e' sempre (simulato - reale) / reale: il reale e' il riferimento.
 * Cio' che il log non sa (inizio delle attivita', costo) non diventa uno zero:
 * la riga resta, marcata come non confrontabile.
 */
import type { EventLogSummary } from "./eventLogTypes";
import type { SimulationSummary } from "../simulationTypes";

export type Fidelity = "close" | "calibrate" | "far";
export type GapFormat = "duration" | "rate" | "currency";
export type NotComparable = "noStart" | "noCost" | "missing";

export type KpiGap = {
  key: "cycleAvg" | "cycleP50" | "cycleP90" | "waitingAvg" | "processingAvg" | "throughput" | "costPerCase";
  format: GapFormat;
  real: number | null;
  simulated: number | null;
  /** (simulato - reale) / reale; null quando il confronto non ha senso. */
  gap: number | null;
  fidelity: Fidelity | null;
  notComparable?: NotComparable;
};

export type ActivityGap = {
  el: string;
  name: string;
  /** Le attivita' del log confluite in questo elemento (piu' di una se aggregate). */
  logNames: string[];
  realCount: number;
  simulatedCount: number;
  realWait: number | null;
  simulatedWait: number | null;
  /** null quando il log non registra l'inizio: la durata contiene l'attesa. */
  realProcessing: number | null;
  simulatedProcessing: number;
  processingGap: number | null;
  waitGap: number | null;
  fidelity: Fidelity | null;
};

export type RealVsSimulated = {
  process: KpiGap[];
  activities: ActivityGap[];
  /** Attivita' del log senza elemento del modello: fuori dal confronto. */
  unmatchedReal: string[];
  /** Attivita' del log abbinate a un elemento che il run non ha mai eseguito. */
  notSimulated: string[];
  /** Elementi simulati che il log non ha mai visto. */
  unobservedSimulated: string[];
  /** Giudizio complessivo: il peggiore fra cycle time medio e P90. */
  fidelity: Fidelity | null;
};

/** Soglie dello scarto relativo: entro il 10% vicino, entro il 25% da calibrare. */
export const FIDELITY_CLOSE = 0.1;
export const FIDELITY_CALIBRATE = 0.25;

export function fidelityOf(gap: number | null): Fidelity | null {
  if (gap === null || !Number.isFinite(gap)) return null;
  // Arrotondato al decimillesimo: 2,2 su 2 e' +10%, non +10,0000001%.
  const size = Math.round(Math.abs(gap) * 10_000) / 10_000;
  if (size <= FIDELITY_CLOSE) return "close";
  return size <= FIDELITY_CALIBRATE ? "calibrate" : "far";
}

const RANK: Record<Fidelity, number> = { close: 0, calibrate: 1, far: 2 };

export function worstFidelity(values: (Fidelity | null)[]): Fidelity | null {
  return values.reduce<Fidelity | null>((worst, value) => {
    if (value === null) return worst;
    return worst === null || RANK[value] > RANK[worst] ? value : worst;
  }, null);
}

export function relativeGap(real: number | null, simulated: number | null): number | null {
  if (real === null || simulated === null || !Number.isFinite(real) || !Number.isFinite(simulated)) return null;
  if (real === 0) return simulated === 0 ? 0 : null;
  return (simulated - real) / real;
}

type Row = Record<string, unknown>;

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function at(source: unknown, ...path: string[]): number | null {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object") return null;
    current = (current as Row)[key];
  }
  return num(current);
}

function rows(summary: unknown): Row[] {
  const value = summary && typeof summary === "object" ? (summary as Row).byActivity : null;
  return Array.isArray(value) ? value.filter((row): row is Row => Boolean(row) && typeof row === "object") : [];
}

function gapRow(key: KpiGap["key"], format: GapFormat, real: number | null, simulated: number | null, notComparable?: NotComparable): KpiGap {
  if (notComparable) return { key, format, real, simulated, gap: null, fidelity: null, notComparable };
  if (real === null || simulated === null) return { key, format, real, simulated, gap: null, fidelity: null, notComparable: "missing" };
  const gap = relativeGap(real, simulated);
  return { key, format, real, simulated, gap, fidelity: fidelityOf(gap) };
}

export function compareRealToSimulated(real: EventLogSummary, simulated: SimulationSummary): RealVsSimulated {
  // Con il solo completamento l'attesa non si separa dalla lavorazione: il log
  // mette tutto in lavorazione, quindi nessuno dei due si confronta.
  const noStart: NotComparable | undefined = real.timing === "complete_only" ? "noStart" : undefined;
  const process: KpiGap[] = [
    gapRow("cycleAvg", "duration", at(real, "cycle", "avg"), at(simulated, "cycle", "avg")),
    gapRow("cycleP50", "duration", at(real, "cycle", "p50"), at(simulated, "cycle", "p50")),
    gapRow("cycleP90", "duration", at(real, "cycle", "p90"), at(simulated, "cycle", "p90")),
    gapRow("waitingAvg", "duration", at(real, "waiting", "avg"), at(simulated, "waiting", "avg"), noStart),
    gapRow("processingAvg", "duration", at(real, "processing", "avg"), at(simulated, "processing", "avg"), noStart),
    gapRow("throughput", "rate", num(real.throughputPerHour), num(simulated.throughputPerHour)),
    gapRow("costPerCase", "currency", real.cost ? num(real.cost.perCase) : null, at(simulated, "cost", "perCase"), real.cost ? undefined : "noCost"),
  ];

  const simulatedByEl = new Map<string, Row>();
  for (const row of rows(simulated)) if (typeof row.el === "string") simulatedByEl.set(row.el, row);

  // Piu' attivita' del log possono finire sullo stesso elemento del modello:
  // si confrontano una volta sola, con medie pesate sulle esecuzioni.
  type Group = { names: string[]; count: number; wait: number; processing: number };
  const groups = new Map<string, Group>();
  const unmatchedReal: string[] = [];
  const notSimulated: string[] = [];
  for (const row of rows(real)) {
    const name = typeof row.name === "string" ? row.name : "";
    const el = typeof row.el === "string" ? row.el : null;
    if (!el) {
      unmatchedReal.push(name);
      continue;
    }
    if (!simulatedByEl.has(el)) {
      notSimulated.push(name || el);
      continue;
    }
    const count = num(row.count) ?? 0;
    const group = groups.get(el) ?? { names: [], count: 0, wait: 0, processing: 0 };
    group.names.push(name || el);
    group.count += count;
    group.wait += (at(row, "wait", "avg") ?? 0) * count;
    group.processing += (at(row, "processing", "avg") ?? 0) * count;
    groups.set(el, group);
  }

  const activities: ActivityGap[] = [...groups.entries()].map(([el, group]) => {
    const twin = simulatedByEl.get(el) as Row;
    const mean = (total: number) => (group.count > 0 ? total / group.count : null);
    // Con il solo completamento la "lavorazione" del log contiene anche l'attesa.
    const realWait = noStart ? null : mean(group.wait);
    const realProcessing = noStart ? null : mean(group.processing);
    const simulatedWait = noStart ? null : at(twin, "wait", "avg");
    const simulatedProcessing = at(twin, "processing", "avg") ?? 0;
    const processingGap = relativeGap(realProcessing, simulatedProcessing);
    const modelName = typeof twin.name === "string" ? twin.name : el;
    return {
      el,
      name: group.names.length === 1 ? group.names[0] : modelName,
      logNames: group.names,
      realCount: group.count,
      simulatedCount: num(twin.count) ?? 0,
      realWait,
      simulatedWait,
      realProcessing,
      simulatedProcessing,
      processingGap,
      waitGap: relativeGap(realWait, simulatedWait),
      fidelity: fidelityOf(processingGap),
    };
  });
  // Prima gli scarti piu' grandi: e' li' che il consulente deve guardare.
  activities.sort((a, b) => Math.abs(b.processingGap ?? 0) - Math.abs(a.processingGap ?? 0));

  const unobservedSimulated = [...simulatedByEl.entries()]
    .filter(([el]) => !groups.has(el))
    .map(([el, row]) => (typeof row.name === "string" ? row.name : el));

  return {
    process,
    activities,
    unmatchedReal,
    notSimulated,
    unobservedSimulated,
    fidelity: worstFidelity(process.filter((row) => row.key === "cycleAvg" || row.key === "cycleP90").map((row) => row.fidelity)),
  };
}

/** Lo scarto con il segno, nella lingua del consulente: "+12%", "-5%", "0%". */
export function signedPercent(gap: number | null, lang: "it" | "en"): string {
  if (gap === null || !Number.isFinite(gap)) return "—";
  return new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US", { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" }).format(gap);
}

/** Il log mappato piu' recente: e' il riferimento reale dell'inspector. */
export function latestMappedLog<T extends { status: string; mapped_at: string | null }>(logs: T[] | undefined): T | null {
  return (logs ?? [])
    .filter((log) => log.status === "mapped" && log.mapped_at)
    .sort((a, b) => (b.mapped_at ?? "").localeCompare(a.mapped_at ?? ""))[0] ?? null;
}
