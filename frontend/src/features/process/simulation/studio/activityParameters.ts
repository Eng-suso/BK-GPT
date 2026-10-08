/**
 * What a run actually simulated for one activity (SIM-20a) — read from the
 * request stored on the run, with the same fallbacks the backend applies
 * (`backend/simulation/ir/from_request.py`): no override means the default
 * duration, a Normal distribution and the first resource; a missing std. dev.
 * is 10% of the mean; a resource without a calendar works the standard one.
 *
 * Pure: no IO, no React.
 */

import { formatDuration } from "../simulationResults";
import { activityProvenance, type FieldProvenance } from "../simulationProvenance";
import type { ScenarioElementProvenance } from "../simulationTypes";

/** Prosimos 2.1 distributions (`DistributionName` in `backend/schemas/simulation.py`). */
export type SimDistribution = "fixed" | "expon" | "uniform" | "norm" | "lognorm" | "gamma";

export type ActivityParameters = {
  meanSeconds: number;
  distribution: SimDistribution;
  /** Spread of the duration; `assumed` = the backend's 10%-of-the-mean default. */
  std: { seconds: number; assumed: boolean } | null;
  /** Bounds the consultant set explicitly (always present for the uniform). */
  bounds: { minSeconds: number; maxSeconds: number } | null;
  resource: {
    name: string;
    amount: number;
    costPerHour: number;
    /** Calendar name; null = the standard Mon–Fri 9–17 calendar. */
    calendar: string | null;
  } | null;
  /** True when the run used the default duration, not a per-task value. */
  usesDefault: boolean;
  provenance: FieldProvenance;
};

const DISTRIBUTIONS: readonly SimDistribution[] = ["fixed", "expon", "uniform", "norm", "lognorm", "gamma"];
const WITH_STD: ReadonlySet<SimDistribution> = new Set(["norm", "lognorm", "gamma"]);
const DEFAULT_STD_SHARE = 0.1;

function record(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter((r): r is Record<string, unknown> => r != null) : [];
}

function num(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNum(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** The run configured this element as a task (gateways and events never are). */
export function hasTaskConfig(request: Record<string, unknown> | null | undefined, elementId: string): boolean {
  return Boolean(elementId) && records(request?.tasks).some((t) => t.element_id === elementId);
}

export function activityParameters(
  request: Record<string, unknown> | null | undefined,
  elementId: string,
  element?: ScenarioElementProvenance,
): ActivityParameters | null {
  // Every stored request carries the default duration; without it the run's
  // configuration is unknown and nothing here would be true.
  if (!request || !elementId || typeof request.default_task_duration_seconds !== "number") return null;
  const defaultMean = request.default_task_duration_seconds;
  const task = records(request.tasks).find((t) => t.element_id === elementId) ?? null;

  const calendars = new Map(records(request.calendars).map((c) => [str(c.id), str(c.name) || str(c.id)]));
  const resources = records(request.resources);
  const pool = resources.length
    ? resources.map((r) => ({
        id: str(r.id),
        name: str(r.name),
        amount: num(r.amount, 1),
        costPerHour: num(r.cost_per_hour, 0),
        calendar: calendars.get(str(r.calendar_id)) ?? null,
      }))
    : [
        {
          id: "",
          name: str(request.resource_name) || "Operatore",
          amount: num(request.resource_amount, 1),
          costPerHour: num(request.default_cost_per_hour, 0),
          calendar: null,
        },
      ];
  const resource = pool.find((r) => r.id && r.id === task?.resource_id) ?? pool[0] ?? null;

  const meanSeconds = Math.max(1, task ? num(task.mean_seconds, defaultMean) : defaultMean);
  const raw = str(task?.distribution);
  const distribution = (DISTRIBUTIONS as readonly string[]).includes(raw) ? (raw as SimDistribution) : "norm";
  const explicitStd = optionalNum(task?.std_seconds);
  const min = optionalNum(task?.min_seconds);
  const max = optionalNum(task?.max_seconds);
  const usesDefault = !task || meanSeconds === defaultMean;

  return {
    meanSeconds,
    distribution,
    std: WITH_STD.has(distribution)
      ? explicitStd != null
        ? { seconds: explicitStd, assumed: false }
        : { seconds: Math.max(1, meanSeconds * DEFAULT_STD_SHARE), assumed: true }
      : null,
    bounds: min != null && max != null ? { minSeconds: min, maxSeconds: max } : null,
    resource: resource
      ? { name: resource.name, amount: resource.amount, costPerHour: resource.costPerHour, calendar: resource.calendar }
      : null,
    usesDefault,
    provenance: activityProvenance(!usesDefault, element),
  };
}

/**
 * A parameter is an input, not a result: under an hour keep the seconds that
 * `formatDuration` drops ("1 min 30 s", not "1 min").
 */
export function formatParameterDuration(totalSeconds: number, lang: "it" | "en"): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const base = formatDuration(seconds, lang);
  const rest = seconds % 60;
  return seconds >= 60 && seconds < 3_600 && rest > 0 ? `${base} ${rest} s` : base;
}
