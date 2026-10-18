import type { Confidence, InputConfidence } from "./simulationProvenance";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";

/**
 * SIM-25: tornado di sensitivita' e valore dell'informazione.
 *
 * Le ipotesi incerte (confidenza bassa o media nella prontezza) si spostano di
 * ±20% una alla volta; il backend mette in coda il run centrale e due varianti
 * per ipotesi, tutte con lo stesso seed. Qui si scelgono le ipotesi e si legge
 * lo studio: la barra piu' lunga e' l'ipotesi che conviene verificare per prima.
 */

export const SENSITIVITY_DELTA = 0.2;
/** Come `SENSITIVITY_MAX_FACTORS` del backend: 2 run per ipotesi piu' il centrale. */
export const SENSITIVITY_MAX_FACTORS = 8;
/** Sotto questa quota del valore centrale una differenza fra due run singoli puo' essere il caso. */
export const NOISE_SHARE = 0.02;

export type SensitivityKind = "duration" | "arrival" | "gateway";

export type SensitivityFactor = {
  kind: SensitivityKind;
  elementId?: string;
  label: string;
  confidence: Confidence;
};

const uncertain = (c: Confidence | undefined): c is "low" | "medium" => c === "low" || c === "medium";

/**
 * Le ipotesi da far variare: prima le basse, poi le medie, al massimo
 * `SENSITIVITY_MAX_FACTORS`. Una decisione guidata da regole o da un timer non
 * ha probabilita' da spostare, e resta fuori.
 */
export function uncertainFactors(
  confidence: InputConfidence,
  template: ScenarioTemplate | null,
  draft: ScenarioDraft,
  arrivalLabel: string,
): SensitivityFactor[] {
  const factors: SensitivityFactor[] = [];
  for (const task of template?.tasks ?? []) {
    const c = confidence.activities[task.element_id]?.confidence;
    if (uncertain(c) && draft.tasks[task.element_id]) {
      factors.push({ kind: "duration", elementId: task.element_id, label: task.name || task.element_id, confidence: c });
    }
  }
  for (const gateway of template?.gateways ?? []) {
    const c = confidence.gateways[gateway.element_id]?.confidence;
    const rules = Object.keys(draft.gatewayRules?.[gateway.element_id] ?? {}).length > 0;
    const branches = Object.keys(draft.gateways[gateway.element_id] ?? {}).length;
    if (uncertain(c) && !rules && !gateway.escalation && branches >= 2) {
      factors.push({ kind: "gateway", elementId: gateway.element_id, label: gateway.name || gateway.element_id, confidence: c });
    }
  }
  const arrival = confidence.globals.arrival.confidence;
  if (uncertain(arrival)) factors.push({ kind: "arrival", label: arrivalLabel, confidence: arrival });

  const rank = (f: SensitivityFactor) => (f.confidence === "low" ? 0 : 1);
  return factors
    .map((f, i) => [f, i] as const)
    .sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j)
    .slice(0, SENSITIVITY_MAX_FACTORS)
    .map(([f]) => f);
}

// --- lettura dello studio ---------------------------------------------------

export type TornadoKpi = "cycle" | "costPerCase";

const KPI: Record<TornadoKpi, (r: SimulationRun) => number | undefined> = {
  cycle: (r) => r.summary?.cycle.avg,
  costPerCase: (r) => r.summary?.cost.perCase,
};

type Mark = { kind: SensitivityKind; element_id?: string | null; label?: string; direction: "low" | "high"; delta: number };

export function sensitivityStudy(run: SimulationRun | null | undefined): string | null {
  const study = run?.request?.sensitivity_study;
  return typeof study === "string" && study ? study : null;
}

function markOf(run: SimulationRun): Mark | null {
  const mark = run.request?.sensitivity;
  if (!mark || typeof mark !== "object") return null;
  const m = mark as Partial<Mark>;
  return m.kind && (m.direction === "low" || m.direction === "high") && typeof m.delta === "number" ? (m as Mark) : null;
}

/**
 * Una variante di uno studio: un'ipotesi spostata apposta. Non e' un risultato
 * dello scenario, quindi resta fuori dal run predefinito e dal confronto del
 * workspace. Il run centrale invece lo e'.
 */
export function isSensitivityVariant(run: SimulationRun): boolean {
  return markOf(run) !== null;
}

/** I run dello studio del run: il centrale e le varianti. */
export function studyMembers(run: SimulationRun | null | undefined, runs: SimulationRun[]): SimulationRun[] {
  const study = sensitivityStudy(run);
  return study ? runs.filter((r) => sensitivityStudy(r) === study) : [];
}

export type TornadoRow = {
  key: string;
  kind: SensitivityKind;
  label: string;
  /** Il KPI con l'ipotesi a -delta e a +delta; undefined finche' il run non e' completo. */
  low?: number;
  high?: number;
  /** |high - low|: quanto il KPI dipende dall'ipotesi. */
  swing: number;
  /** La differenza sta sotto `NOISE_SHARE` del centrale: non distinguibile dal caso. */
  negligible: boolean;
};

export type Tornado = {
  center?: number;
  delta: number;
  rows: TornadoRow[];
  total: number;
  completed: number;
  failed: number;
};

export function buildTornado(members: SimulationRun[], kpi: TornadoKpi): Tornado {
  const done = (r: SimulationRun) => r.status === "completed" && r.summary != null;
  const value = (r: SimulationRun | undefined) => {
    const v = r && done(r) ? KPI[kpi](r) : undefined;
    return typeof v === "number" && Number.isFinite(v) ? v : undefined;
  };
  const central = members.find((r) => markOf(r) === null);
  const center = value(central);
  const byKey = new Map<string, { kind: SensitivityKind; label: string; low?: SimulationRun; high?: SimulationRun }>();
  let delta = 0.2;
  for (const run of members) {
    const mark = markOf(run);
    if (!mark) continue;
    delta = mark.delta;
    const key = `${mark.kind}:${mark.element_id ?? ""}`;
    const row = byKey.get(key) ?? { kind: mark.kind, label: mark.label || mark.element_id || "", low: undefined, high: undefined };
    row[mark.direction] = run;
    byKey.set(key, row);
  }
  const rows: TornadoRow[] = [...byKey.entries()].map(([key, row]) => {
    const low = value(row.low);
    const high = value(row.high);
    const swing = low !== undefined && high !== undefined ? Math.abs(high - low) : 0;
    return {
      key,
      kind: row.kind,
      label: row.label,
      low,
      high,
      swing,
      negligible: center !== undefined && center > 0 && low !== undefined && high !== undefined && swing < NOISE_SHARE * center,
    };
  });
  rows.sort((a, b) => b.swing - a.swing);
  return {
    center,
    delta,
    rows,
    total: members.length,
    completed: members.filter(done).length,
    failed: members.filter((r) => r.status === "failed").length,
  };
}
