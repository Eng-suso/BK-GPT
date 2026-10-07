/**
 * Input Confidence (Phase 5) — pure roll-up.
 *
 * The backend says where each element's *structure* came from, on the Simulation
 * IR's five-level scale (`declared` by discovery, `estimated` by the model, and
 * `observed` / `inferred` once an event log backs it) and, for gateways, how
 * certain the discovered outcomes are. This module layers the local scenario draft on top — "has the
 * consultant moved this field off its default?" — and produces:
 *
 *   • a per-field provenance badge (origin + confidence)
 *   • a Simulation Readiness roll-up (one row per parameter family + an overall)
 *
 * No IO, no React. `buildInputConfidence` is the whole contract.
 */

import type {
  ParameterSourceRef,
  ProvenanceOrigin,
  ScenarioElementProvenance,
  ScenarioProvenance,
  ScenarioTemplate,
} from "./simulationTypes";
import { DEFAULT_SCENARIO, scenarioResourceIssues, type ScenarioDraft } from "./simulationScenario";

/**
 * One scale for every badge (SIM-38): the IR's five origins, plus `default` for
 * a value nobody set — the undeclared assumption the readiness roll-up counts.
 *
 *   observed  measured on an event log
 *   inferred  derived with statistics or mining
 *   declared  said in an interview or written in a document
 *   estimated proposed by a model, or a plausible guess on a known structure
 *   manual    entered by the consultant
 */
export type FieldOrigin = ProvenanceOrigin | "default";

export type Confidence = "high" | "medium" | "low";

export type FieldProvenance = {
  origin: FieldOrigin;
  confidence: Confidence;
  /** What backs the value: interview steps, claims, event logs. */
  sources?: ParameterSourceRef[];
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

/** Discovery or data back the element; `estimated` means the model made it up. */
function isGrounded(el: ScenarioElementProvenance | undefined): el is ScenarioElementProvenance {
  return el != null && el.provenance.origin !== "estimated";
}

function sourcesOf(el: ScenarioElementProvenance | undefined): ParameterSourceRef[] | undefined {
  return el?.provenance.sources.length ? el.provenance.sources : undefined;
}

/** Provenance of one activity's duration: `custom` = moved off the default. */
export function activityProvenance(
  custom: boolean,
  el: ScenarioElementProvenance | undefined,
): FieldProvenance {
  const evidence = el?.evidence?.length ? el.evidence : undefined;
  if (!isGrounded(el)) {
    return custom ? { origin: "manual", confidence: "medium" } : { origin: "default", confidence: "low" };
  }
  const grounding = { evidence, sources: sourcesOf(el), hintRef: el.hint_ref };
  if (custom) return { origin: "manual", confidence: "high", ...grounding };
  if (el.provenance.origin === "observed" || el.provenance.origin === "inferred") {
    // the number itself comes from data, not just the structure
    return { origin: el.provenance.origin, confidence: el.provenance.confidence ?? el.confidence, ...grounding };
  }
  // structure is real, but discovery never captured a duration
  return { origin: "estimated", confidence: "medium", ...grounding };
}

function gatewayProvenance(
  touched: boolean,
  el: ScenarioElementProvenance | undefined,
): FieldProvenance {
  const open = el?.open_questions ?? 0;
  const note = open > 0 ? `${open}` : undefined; // rendered with i18n by the caller

  if (!isGrounded(el)) {
    return touched
      ? { origin: "manual", confidence: "medium", note }
      : { origin: "estimated", confidence: "low", note };
  }
  const grounding = {
    evidence: el.evidence?.length ? el.evidence : undefined,
    sources: sourcesOf(el),
    hintRef: el.hint_ref,
  };
  if (el.confidence === "high") {
    return { origin: touched ? "manual" : el.provenance.origin, confidence: "high", ...grounding };
  }
  return {
    origin: touched ? "manual" : el.provenance.origin,
    confidence: el.confidence === "medium" || touched ? "medium" : "low",
    note,
    ...grounding,
  };
}

function globalField(changed: boolean, whenSet: Confidence): FieldProvenance {
  return changed
    ? { origin: "manual", confidence: whenSet }
    : { origin: "default", confidence: "low" };
}

function resourcesField(draft: ScenarioDraft): FieldProvenance {
  const issues = scenarioResourceIssues(draft);
  if (issues.missingResources) return { origin: "default", confidence: "low" };
  if (issues.pending > 0 || issues.unassigned > 0) {
    // pools and lanes of the BPMN are declared structure, never staffing
    return { origin: draft.resources.some((r) => r.source) ? "declared" : "estimated", confidence: "low" };
  }
  return { origin: "manual", confidence: "high" };
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
          isGrounded(byId.get(el.element_id)) ? "high" : "low",
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
      isGrounded(byId.get(el.element_id)) ? "high" : "low",
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
