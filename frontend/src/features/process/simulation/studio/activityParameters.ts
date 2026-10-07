/**
 * What a run actually simulated for one activity (SIM-20a) — read from the
 * request stored on the run, with the same fallbacks the backend applies
 * (`backend/simulation/ir/from_request.py`): no override means the default
 * duration, a Normal distribution and the first resource.
 *
 * Pure: no IO, no React.
 */

import { activityProvenance, type FieldProvenance } from "../simulationProvenance";
import type { ScenarioElementProvenance } from "../simulationTypes";

export type SimDistribution = "norm" | "expon" | "fixed";

export type ActivityParameters = {
  meanSeconds: number;
  distribution: SimDistribution;
  /** Normal only: the backend fixes the std. dev. at 10% of the mean. */
  stdShareOfMean: number | null;
  resource: { name: string; amount: number; costPerHour: number } | null;
  /** True when the run used the default duration, not a per-task value. */
  usesDefault: boolean;
  provenance: FieldProvenance;
};

const DISTRIBUTIONS: readonly SimDistribution[] = ["norm", "expon", "fixed"];
const NORMAL_STD_SHARE = 0.1;

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
  if (!request || !elementId) return null;
  const defaultMean = num(request.default_task_duration_seconds, 900);
  const task = records(request.tasks).find((t) => t.element_id === elementId) ?? null;

  const resources = records(request.resources);
  const pool = resources.length
    ? resources.map((r) => ({
        id: str(r.id),
        name: str(r.name),
        amount: num(r.amount, 1),
        costPerHour: num(r.cost_per_hour, 0),
      }))
    : [
        {
          id: "",
          name: str(request.resource_name) || "Operatore",
          amount: num(request.resource_amount, 1),
          costPerHour: num(request.default_cost_per_hour, 0),
        },
      ];
  const resource = pool.find((r) => r.id && r.id === task?.resource_id) ?? pool[0] ?? null;

  const meanSeconds = Math.max(1, task ? num(task.mean_seconds, defaultMean) : defaultMean);
  const raw = str(task?.distribution);
  const distribution = (DISTRIBUTIONS as readonly string[]).includes(raw) ? (raw as SimDistribution) : "norm";
  const usesDefault = !task || meanSeconds === defaultMean;

  return {
    meanSeconds,
    distribution,
    stdShareOfMean: distribution === "norm" ? NORMAL_STD_SHARE : null,
    resource: resource ? { name: resource.name, amount: resource.amount, costPerHour: resource.costPerHour } : null,
    usesDefault,
    provenance: activityProvenance(!usesDefault, element),
  };
}
