/**
 * Input Confidence (Phase 5) — pure roll-up.
 *
 * The backend says where each element's *structure* came from (discovery
 * interview vs. model inference) and, for gateways, how certain the discovered
 * outcomes are. This module layers the local scenario draft on top — "has the
 * consultant moved this field off its default?" — and produces:
 *
 *   • a per-field provenance badge (source + confidence)
 *   • a Simulation Readiness roll-up (one row per parameter family + an overall)
 *
 * No IO, no React. `buildInputConfidence` is the whole contract.
 */

import type {
  ScenarioElementProvenance,
  ScenarioProvenance,
  ScenarioTemplate,
} from "./simulationTypes";
import { DEFAULT_SCENARIO, type ScenarioDraft } from "./simulationScenario";

export type ProvenanceSource =
  | "interview" // structure + parameter both grounded in discovery
  | "confirmed" // consultant set this value explicitly
  | "inferred" // model inferred it, not yet confirmed
  | "estimated" // a plausible guess on top of a known structure
  | "default"; // untouched fallback

export type Confidence = "high" | "medium" | "low";

export type FieldProvenance = {
  source: ProvenanceSource;
  confidence: Confidence;
  evidence?: string[];
  /** Short human note, e.g. "2 esiti da validare". */
  note?: string;
  hintRef?: ScenarioElementProvenance["hint_ref"];
};

export type ReadinessKey =
  | "structure"
  | "durations"
  | "resources"
  | "arrivals"
  | "gateways";

export type ReadinessRow = {
  key: ReadinessKey;
  /** 0–100. */
  pct: number;
  confidence: Confidence;
  /** count of fields in this family still weak (low/medium). */
  flagged: number;
};

export type InputConfidence = {
  hasDiscovery: boolean;
  activities: Record<string, FieldProvenance>;
  gateways: Record<string, FieldProvenance>;
  globals: {
    cases: FieldProvenance;
    arrival: FieldProvenance;
    defaultDuration: FieldProvenance;
  };
  resources: FieldProvenance;
  readiness: {
    rows: ReadinessRow[];
    overall: Confidence;
    /** element ids whose parameter is still low-confidence — deep-link targets. */
    lowConfidenceElementIds: string[];
  };
};

const CONFIDENCE_WEIGHT: Record<Confidence, number> = {
  high: 1,
  medium: 0.6,
  low: 0.25,
};

function band(pct: number): Confidence {
  // Roll-up thresholds: a fully-discovered structure with only estimated
  // durations tops out near 60%, so "medium" starts lower than a raw score.
  if (pct >= 75) return "high";
  if (pct >= 45) return "medium";
  return "low";
}

function weightToPct(values: Confidence[]): number {
  if (values.length === 0) return 0;
  const sum = values.reduce((acc, c) => acc + CONFIDENCE_WEIGHT[c], 0);
  return Math.round((sum / values.length) * 100);
}

function elementIndex(
  provenance: ScenarioProvenance | null,
): Map<string, ScenarioElementProvenance> {
  const map = new Map<string, ScenarioElementProvenance>();
  for (const el of provenance?.elements ?? []) map.set(el.element_id, el);
  return map;
}

/** Even baseline `seedDraftFromTemplate` writes for an untouched gateway. */
function isEvenSplit(values: number[]): boolean {
  if (values.length === 0) return true;
  const even = 100 / values.length;
  return values.every((v) => Math.abs(v - even) <= 0.75);
}

function activityProvenance(
  custom: boolean,
  el: ScenarioElementProvenance | undefined,
): FieldProvenance {
  const grounded = el?.origin === "interview";
  const evidence = el?.evidence?.length ? el.evidence : undefined;
  if (grounded && custom) {
    return { source: "confirmed", confidence: "high", evidence, hintRef: el?.hint_ref };
  }
  if (grounded) {
    // structure is real, but discovery never captured a duration
    return { source: "estimated", confidence: "medium", evidence, hintRef: el?.hint_ref };
  }
  if (custom) return { source: "confirmed", confidence: "medium" };
  return { source: "default", confidence: "low" };
}

function gatewayProvenance(
  touched: boolean,
  el: ScenarioElementProvenance | undefined,
): FieldProvenance {
  const open = el?.open_questions ?? 0;
  const note = open > 0 ? `${open}` : undefined; // rendered with i18n by the caller
  const evidence = el?.evidence?.length ? el.evidence : undefined;

  if (!el || el.origin === "ai_inferred") {
    return touched
      ? { source: "confirmed", confidence: "medium", note }
      : { source: "estimated", confidence: "low", note };
  }
  if (el.confidence === "high") {
    return {
      source: touched ? "confirmed" : "interview",
      confidence: "high",
      evidence,
      hintRef: el.hint_ref,
    };
  }
  if (el.confidence === "medium") {
    return {
      source: touched ? "confirmed" : "inferred",
      confidence: "medium",
      evidence,
      note,
      hintRef: el.hint_ref,
    };
  }
  return {
    source: touched ? "confirmed" : "estimated",
    confidence: touched ? "medium" : "low",
    evidence,
    note,
    hintRef: el.hint_ref,
  };
}

function globalField(changed: boolean, whenSet: Confidence): FieldProvenance {
  return changed
    ? { source: "confirmed", confidence: whenSet }
    : { source: "default", confidence: "low" };
}

function resourcesField(draft: ScenarioDraft): FieldProvenance {
  const base = DEFAULT_SCENARIO.resources;
  const untouched =
    draft.resources.length === base.length &&
    draft.resources.every((r, i) => {
      const b = base[i];
      return (
        b &&
        r.costPerHour === b.costPerHour &&
        r.amount === b.amount &&
        r.name === b.name
      );
    });
  return untouched
    ? { source: "default", confidence: "low" }
    : { source: "confirmed", confidence: "high" };
}

export function buildInputConfidence(
  draft: ScenarioDraft,
  template: ScenarioTemplate | null,
  provenance: ScenarioProvenance | null,
): InputConfidence {
  const byId = elementIndex(provenance);
  const tasks = template?.tasks ?? [];
  const gateways = template?.gateways ?? [];

  const activities: Record<string, FieldProvenance> = {};
  for (const task of tasks) {
    const cfg = draft.tasks[task.element_id];
    const custom =
      cfg != null && cfg.meanMinutes !== draft.defaultTaskMinutes;
    activities[task.element_id] = activityProvenance(custom, byId.get(task.element_id));
  }

  const gatewayFields: Record<string, FieldProvenance> = {};
  for (const gateway of gateways) {
    const cfg = draft.gateways[gateway.element_id];
    const values = gateway.branches.map((b) => cfg?.[b.flow_id] ?? 0);
    const touched = cfg != null && !isEvenSplit(values);
    gatewayFields[gateway.element_id] = gatewayProvenance(
      touched,
      byId.get(gateway.element_id),
    );
  }

  const globals = {
    cases: globalField(draft.totalCases !== DEFAULT_SCENARIO.totalCases, "high"),
    arrival: globalField(
      draft.arrivalIntervalMinutes !== DEFAULT_SCENARIO.arrivalIntervalMinutes,
      "high",
    ),
    defaultDuration: globalField(
      draft.defaultTaskMinutes !== DEFAULT_SCENARIO.defaultTaskMinutes,
      "medium",
    ),
  };
  const resources = resourcesField(draft);

  // --- readiness roll-up --------------------------------------------------
  const structurePct = provenance
    ? weightToPct(
        [...tasks, ...gateways].map((el) =>
          byId.get(el.element_id)?.origin === "interview" ? "high" : "low",
        ),
      )
    : 0;

  const durationConfidences = Object.values(activities).map((f) => f.confidence);
  const gatewayConfidences = Object.values(gatewayFields).map((f) => f.confidence);
  const arrivalConfidences: Confidence[] = [
    globals.cases.confidence,
    globals.arrival.confidence,
  ];

  const rows: ReadinessRow[] = [
    row("structure", structurePct, countWeak([...tasks, ...gateways].map((el) =>
      byId.get(el.element_id)?.origin === "interview" ? "high" : "low",
    ))),
    row("durations", weightToPct(durationConfidences), countWeak(durationConfidences)),
    row("resources", weightToPct([resources.confidence]), countWeak([resources.confidence])),
    row("arrivals", weightToPct(arrivalConfidences), countWeak(arrivalConfidences)),
    ...(gateways.length
      ? [row("gateways", weightToPct(gatewayConfidences), countWeak(gatewayConfidences))]
      : []),
  ];

  const overall = rollUpOverall(rows, structurePct, Boolean(provenance));

  const lowConfidenceElementIds = [
    ...tasks
      .filter((t) => activities[t.element_id]?.confidence === "low")
      .map((t) => t.element_id),
    ...gateways
      .filter((g) => gatewayFields[g.element_id]?.confidence !== "high")
      .map((g) => g.element_id),
  ];

  return {
    hasDiscovery: Boolean(provenance?.has_discovery),
    activities,
    gateways: gatewayFields,
    globals,
    resources,
    readiness: { rows, overall, lowConfidenceElementIds },
  };
}

function row(key: ReadinessKey, pct: number, flagged: number): ReadinessRow {
  return { key, pct, confidence: band(pct), flagged };
}

function countWeak(values: Confidence[]): number {
  return values.filter((c) => c !== "high").length;
}

function rollUpOverall(
  rows: ReadinessRow[],
  structurePct: number,
  hasProvenance: boolean,
): Confidence {
  if (!hasProvenance) return "low";
  if (structurePct < 50) return "low";
  const weighted =
    rows.reduce(
      (acc, r) => acc + r.pct * (r.key === "structure" ? 1.5 : 1),
      0,
    ) / (rows.length + 0.5);
  const base = band(weighted);
  const lows = rows.filter((r) => r.confidence === "low").length;
  if (lows >= 3) return "low";
  if (lows >= 2 && base === "high") return "medium";
  if (base === "high" && rows.some((r) => r.pct < 45)) return "medium";
  return base;
}
