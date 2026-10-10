import { z } from "zod";

import { http } from "@/lib/http";

import { compareGroups, groupMembers, replicationIntervals, KPI_BETTER, type DeltaInterval, type Interval, type ReplicationKpi } from "./replications";
import type { ScenarioPatchOp } from "./scenarioPatch";
import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-14: il workspace degli scenari AS-IS | A | B | C di un processo.
 * Backend: `backend/simulation/scenarios.py`, route `/simulation-scenarios`.
 */

const patchOpSchema = z.object({
  op: z.enum(["set", "remove", "order"]),
  path: z.array(z.union([z.string(), z.object({ id: z.string() })])),
  value: z.unknown().optional(),
  ids: z.array(z.string()).optional(),
});

export const workspaceScenarioSchema = z.object({
  id: z.number(),
  kind: z.enum(["baseline", "alternative"]),
  label: z.string(),
  name: z.string(),
  revision: z.number(),
  draft: z.record(z.string(), z.unknown()),
  patch: z.array(patchOpSchema),
  conflicts: z.array(z.number()),
  created_at: z.string(),
  updated_at: z.string(),
});

export const scenarioWorkspaceSchema = z.object({
  bpmn_model_id: z.string(),
  seed: z.number().nullable(),
  baseline: workspaceScenarioSchema.nullable(),
  alternatives: z.array(workspaceScenarioSchema),
});

export type WorkspaceScenario = z.infer<typeof workspaceScenarioSchema>;
export type ScenarioWorkspace = z.infer<typeof scenarioWorkspaceSchema>;

/** Le alternative oltre l'AS-IS: A–E, come il backend. */
export const MAX_ALTERNATIVES = 5;

const base = (bpmnModelId: string) => `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-scenarios`;
const parse = (raw: unknown) => scenarioWorkspaceSchema.parse(raw);

export async function fetchScenarioWorkspace(bpmnModelId: string): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(base(bpmnModelId)));
}

export async function putScenarioBaseline(
  bpmnModelId: string,
  body: { name: string; draft: object; revision?: number; seed?: number },
): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/baseline`, { method: "PUT", body }));
}

export async function createWorkspaceScenario(
  bpmnModelId: string,
  body: { name: string; patch: ScenarioPatchOp[] },
): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(base(bpmnModelId), { method: "POST", body }));
}

export async function updateWorkspaceScenario(
  bpmnModelId: string,
  scenarioId: number,
  body: { name?: string; patch?: ScenarioPatchOp[]; revision: number },
): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}`, { method: "PATCH", body }));
}

export async function deleteWorkspaceScenario(bpmnModelId: string, scenarioId: number): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}`, { method: "DELETE" }));
}

export function workspaceScenarios(workspace: ScenarioWorkspace | null | undefined): WorkspaceScenario[] {
  if (!workspace?.baseline) return [];
  return [workspace.baseline, ...workspace.alternatives];
}

/** Come lo scenario si chiama nei run e nei menu: "AS-IS" o "A · +1 approvatore". */
export function scenarioDisplayName(scenario: Pick<WorkspaceScenario, "kind" | "label" | "name">): string {
  return scenario.kind === "baseline" ? scenario.name : `${scenario.label} · ${scenario.name}`;
}

export type WorkspaceScenarioRef = { id: number; revision: number; baseline_revision: number };

export function scenarioRef(workspace: ScenarioWorkspace, scenario: WorkspaceScenario): WorkspaceScenarioRef {
  return { id: scenario.id, revision: scenario.revision, baseline_revision: workspace.baseline?.revision ?? scenario.revision };
}

export function runScenarioRef(run: SimulationRun): WorkspaceScenarioRef | null {
  const ref = run.request?.workspace_scenario as Partial<WorkspaceScenarioRef> | null | undefined;
  return ref && typeof ref.id === "number" && typeof ref.revision === "number" && typeof ref.baseline_revision === "number"
    ? { id: ref.id, revision: ref.revision, baseline_revision: ref.baseline_revision }
    : null;
}

export type ScenarioRunStatus = "never" | "pending" | "failed" | "stale" | "current";

export type ScenarioRuns = {
  /** Il run piu' recente dello scenario e, se ripetuto, il suo gruppo in ordine. */
  latest: SimulationRun | null;
  members: SimulationRun[];
  completed: SimulationRun[];
  status: ScenarioRunStatus;
};

/** L'ultimo run (o gruppo di ripetizioni) di uno scenario e se e' ancora valido. */
export function scenarioRuns(workspace: ScenarioWorkspace, scenario: WorkspaceScenario, runs: SimulationRun[]): ScenarioRuns {
  const own = runs.filter((run) => runScenarioRef(run)?.id === scenario.id);
  const latest = own.reduce<SimulationRun | null>((best, run) => (!best || run.id > best.id ? run : best), null);
  if (!latest) return { latest: null, members: [], completed: [], status: "never" };
  const group = groupMembers(latest, runs);
  const members = group.length ? group : [latest];
  const completed = members.filter((run) => run.status === "completed" && run.summary);
  const ref = runScenarioRef(latest)!;
  const current = ref.revision === scenario.revision && ref.baseline_revision === workspace.baseline?.revision;
  const status: ScenarioRunStatus = members.some((run) => run.status === "pending")
    ? "pending"
    : completed.length === 0
      ? "failed"
      : current
        ? "current"
        : "stale";
  return { latest, members, completed, status };
}

export const WORKSPACE_KPIS: ReplicationKpi[] = ["cycle", "waiting", "costPerCase", "throughput"];

const KPI_SUMMARY: Record<ReplicationKpi, (run: SimulationRun) => number | undefined> = {
  cycle: (run) => run.summary?.cycle.avg,
  waiting: (run) => run.summary?.waiting.avg,
  costPerCase: (run) => run.summary?.cost.perCase,
  throughput: (run) => run.summary?.throughputPerHour,
};

export type ScenarioValue = {
  /** Media sulle ripetizioni completate, o il valore dell'unico run. */
  mean: number;
  /** Mezza ampiezza al 95%: solo con almeno due ripetizioni. */
  interval: Interval | null;
};

export type ScenarioDelta =
  | { kind: "interval"; value: DeltaInterval; paired: boolean }
  | { kind: "single"; delta: number; direction: "better" | "worse" | "same" };

/** Il valore di un KPI per lo scenario, dalle sue ripetizioni completate. */
export function scenarioValue(results: ScenarioRuns, kpi: ReplicationKpi): ScenarioValue | null {
  const values = results.completed.map(KPI_SUMMARY[kpi]).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!values.length) return null;
  const interval = replicationIntervals(results.completed)[kpi];
  return { mean: values.reduce((a, b) => a + b, 0) / values.length, interval };
}

/**
 * La differenza scenario − AS-IS per ogni KPI. Con almeno due ripetizioni per
 * parte: intervallo al 95% (a coppie se gli stessi seed, altrimenti Welch) e
 * "migliore" solo se esclude lo zero. Con un run solo: il delta secco, che la UI
 * dice non difendibile.
 */
export function scenarioDeltas(asIs: ScenarioRuns, scenario: ScenarioRuns, runs: SimulationRun[]): { kpis: Record<ReplicationKpi, ScenarioDelta | null>; paired: boolean | null } {
  const empty = { cycle: null, waiting: null, costPerCase: null, throughput: null };
  if (!asIs.latest || !scenario.latest || !asIs.completed.length || !scenario.completed.length) return { kpis: empty, paired: null };
  const grouped = compareGroups(asIs.latest, scenario.latest, runs);
  if (grouped) {
    const kpis = { ...empty } as Record<ReplicationKpi, ScenarioDelta | null>;
    for (const kpi of WORKSPACE_KPIS) {
      const value = grouped.kpis[kpi];
      kpis[kpi] = value ? { kind: "interval", value, paired: grouped.paired } : null;
    }
    return { kpis, paired: grouped.paired };
  }
  const kpis = { ...empty } as Record<ReplicationKpi, ScenarioDelta | null>;
  for (const kpi of WORKSPACE_KPIS) {
    const a = scenarioValue(asIs, kpi);
    const b = scenarioValue(scenario, kpi);
    if (!a || !b) continue;
    const delta = b.mean - a.mean;
    const better = KPI_BETTER[kpi] === "lower" ? delta < 0 : delta > 0;
    kpis[kpi] = { kind: "single", delta, direction: delta === 0 ? "same" : better ? "better" : "worse" };
  }
  return { kpis, paired: null };
}

/** Gli elementi del BPMN che lo scenario cambia (attivita' e decisioni), per l'overlay e l'inspector. */
export function changedElements(scenario: Pick<WorkspaceScenario, "patch">): Set<string> {
  const ids = new Set<string>();
  for (const op of scenario.patch) {
    const [section, element] = op.path;
    if ((section === "tasks" || section === "gateways" || section === "gatewayRules") && typeof element === "string") ids.add(element);
  }
  return ids;
}
