import { z } from "zod";

import { http } from "@/lib/http";

import { isSensitivityVariant } from "./sensitivity";
import { compareGroups, groupMembers, replicationIntervals, KPI_BETTER, type DeltaInterval, type Interval, type ReplicationKpi } from "./replications";
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

const outcomeKpiSchema = z.enum(["cycle", "waiting", "costPerCase", "throughput"]);

/** SIM-28: l'alternativa implementata, con quanto aveva ragione la previsione. Variazioni relative. */
export const scenarioOutcomeSchema = z.object({
  implemented_on: z.string(),
  recorded_at: z.string(),
  as_is_run_id: z.number().nullable().optional(),
  alternative_run_id: z.number().nullable().optional(),
  before: z.object({ event_log_id: z.string(), name: z.string(), cases: z.number() }),
  after: z.object({ event_log_id: z.string(), name: z.string(), cases: z.number() }),
  kpis: z.array(z.object({
    kpi: outcomeKpiSchema,
    predicted_change: z.number(),
    predicted_low: z.number().nullable().optional(),
    predicted_high: z.number().nullable().optional(),
    before: z.number().nullable().optional(),
    after: z.number().nullable().optional(),
    observed_change: z.number().nullable().optional(),
    error: z.number().nullable().optional(),
    within: z.boolean().nullable().optional(),
  })),
});
export type ScenarioOutcome = z.infer<typeof scenarioOutcomeSchema>;

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
  outcome: scenarioOutcomeSchema.nullable().optional(),
});

export const scenarioWorkspaceSchema = z.object({
  bpmn_model_id: z.string(),
  /** SIM-14b: l'impronta del BPMN salvato; un run con un'altra impronta e' da rifare. */
  bpmn_fingerprint: z.string().nullable().optional(),
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
  body: { name: string; patch: WorkspaceScenario["patch"] },
): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(base(bpmnModelId), { method: "POST", body }));
}

export async function updateWorkspaceScenario(
  bpmnModelId: string,
  scenarioId: number,
  body: { name?: string; patch?: WorkspaceScenario["patch"]; revision: number },
): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}`, { method: "PATCH", body }));
}

export async function deleteWorkspaceScenario(bpmnModelId: string, scenarioId: number): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}`, { method: "DELETE" }));
}

export type PredictedKpi = { as_is: number; alternative: number; half?: number };
export type ScenarioOutcomeInput = {
  implemented_on: string;
  before_event_log_id: string;
  after_event_log_id: string;
  as_is_run_id: number | null;
  alternative_run_id: number | null;
  predicted: Partial<Record<ReplicationKpi, PredictedKpi>>;
};

/** SIM-28: registra l'alternativa come implementata; il server misura il prima e il dopo dal log reale. */
export async function putScenarioOutcome(bpmnModelId: string, scenarioId: number, body: ScenarioOutcomeInput): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}/outcome`, { method: "PUT", body }));
}

export async function deleteScenarioOutcome(bpmnModelId: string, scenarioId: number): Promise<ScenarioWorkspace> {
  return parse(await http<unknown>(`${base(bpmnModelId)}/${scenarioId}/outcome`, { method: "DELETE" }));
}

/**
 * SIM-28: la previsione con cui l'alternativa e' stata scelta, come la mostra il
 * workspace: media dell'AS-IS e dell'alternativa e, con le ripetizioni, la mezza
 * ampiezza della differenza. Solo i KPI che entrambi gli scenari hanno.
 */
export function predictedSnapshot(asIs: ScenarioRuns, alternative: ScenarioRuns, deltas: ReturnType<typeof scenarioDeltas>): Partial<Record<ReplicationKpi, PredictedKpi>> {
  const out: Partial<Record<ReplicationKpi, PredictedKpi>> = {};
  for (const kpi of WORKSPACE_KPIS) {
    const a = scenarioValue(asIs, kpi);
    const b = scenarioValue(alternative, kpi);
    if (!a || !b || !(a.mean > 0)) continue;
    const delta = deltas.kpis[kpi];
    out[kpi] = { as_is: a.mean, alternative: b.mean, ...(delta?.kind === "interval" ? { half: delta.value.half } : {}) };
  }
  return out;
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

/** Il riferimento del run: senza AS-IS non c'e' workspace, quindi nemmeno uno scenario da citare. */
export function scenarioRef(workspace: ScenarioWorkspace, scenario: WorkspaceScenario): WorkspaceScenarioRef | null {
  return workspace.baseline ? { id: scenario.id, revision: scenario.revision, baseline_revision: workspace.baseline.revision } : null;
}

/** Il seed comune piu' alto: lo stesso `WORKSPACE_SEED_MAX` del backend (intero a 32 bit meno 20 ripetizioni). */
export const WORKSPACE_SEED_MAX = 2 ** 31 - 1 - 20;

export function runScenarioRef(run: SimulationRun): WorkspaceScenarioRef | null {
  const ref = run.request?.workspace_scenario as Partial<WorkspaceScenarioRef> | null | undefined;
  return ref && typeof ref.id === "number" && typeof ref.revision === "number" && typeof ref.baseline_revision === "number"
    ? { id: ref.id, revision: ref.revision, baseline_revision: ref.baseline_revision }
    : null;
}

export type ScenarioRunStatus = "never" | "pending" | "failed" | "stale" | "current";

/** L'impronta del BPMN che il run ha simulato; assente per i run anteriori a SIM-14b. */
export function runBpmnFingerprint(run: SimulationRun | null | undefined): string | null {
  const value = run?.request?.bpmn_fingerprint;
  return typeof value === "string" && value ? value : null;
}

/** Due impronte diverse, quando entrambe ci sono: un run anteriore all'impronta non si accusa. */
function differentBpmn(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a !== b);
}

export type ScenarioRuns = {
  /** Il run piu' recente dello scenario e, se ripetuto, il suo gruppo in ordine. */
  latest: SimulationRun | null;
  members: SimulationRun[];
  completed: SimulationRun[];
  status: ScenarioRunStatus;
  /** Il run e' partito da un disegno diverso da quello salvato oggi. */
  bpmnChanged: boolean;
};

/** L'ultimo run (o gruppo di ripetizioni) di uno scenario e se e' ancora valido. */
export function scenarioRuns(workspace: ScenarioWorkspace, scenario: WorkspaceScenario, runs: SimulationRun[]): ScenarioRuns {
  // Una variante di sensitivita' (SIM-25) sposta un'ipotesi apposta: non e' un risultato dello scenario.
  const own = runs.filter((run) => runScenarioRef(run)?.id === scenario.id && !isSensitivityVariant(run));
  const latest = own.reduce<SimulationRun | null>((best, run) => (!best || run.id > best.id ? run : best), null);
  if (!latest) return { latest: null, members: [], completed: [], status: "never", bpmnChanged: false };
  const group = groupMembers(latest, runs);
  const members = group.length ? group : [latest];
  const completed = members.filter((run) => run.status === "completed" && run.summary);
  const ref = runScenarioRef(latest)!;
  const bpmnChanged = differentBpmn(runBpmnFingerprint(latest), workspace.bpmn_fingerprint);
  const current = ref.revision === scenario.revision && ref.baseline_revision === workspace.baseline?.revision && !bpmnChanged;
  const status: ScenarioRunStatus = members.some((run) => run.status === "pending")
    ? "pending"
    : completed.length === 0
      ? "failed"
      : current
        ? "current"
        : "stale";
  return { latest, members, completed, status, bpmnChanged };
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
 * dice non difendibile. Se i due run partono da versioni diverse dell'AS-IS o
 * da disegni diversi del processo nessun delta: confronterebbe due modelli
 * diversi (`mismatch`).
 * `comparisons`: quante alternative si confrontano insieme con l'AS-IS, per
 * l'intervallo corretto con Bonferroni.
 */
export function scenarioDeltas(asIs: ScenarioRuns, scenario: ScenarioRuns, runs: SimulationRun[], comparisons = 1): { kpis: Record<ReplicationKpi, ScenarioDelta | null>; paired: boolean | null; mismatch: boolean } {
  const empty = { cycle: null, waiting: null, costPerCase: null, throughput: null };
  if (!asIs.latest || !scenario.latest || !asIs.completed.length || !scenario.completed.length) return { kpis: empty, paired: null, mismatch: false };
  const otherBaseline = runScenarioRef(asIs.latest)?.baseline_revision !== runScenarioRef(scenario.latest)?.baseline_revision;
  if (otherBaseline || differentBpmn(runBpmnFingerprint(asIs.latest), runBpmnFingerprint(scenario.latest))) return { kpis: empty, paired: null, mismatch: true };
  const grouped = compareGroups(asIs.latest, scenario.latest, runs, comparisons);
  if (grouped) {
    const kpis = { ...empty } as Record<ReplicationKpi, ScenarioDelta | null>;
    for (const kpi of WORKSPACE_KPIS) {
      const value = grouped.kpis[kpi];
      kpis[kpi] = value ? { kind: "interval", value, paired: grouped.paired } : null;
    }
    return { kpis, paired: grouped.paired, mismatch: false };
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
  return { kpis, paired: null, mismatch: false };
}

/** Le alternative che entrano nel confronto con l'AS-IS: almeno un run completato, sulla stessa versione dell'AS-IS. */
export function comparisonCount(asIs: ScenarioRuns | null, alternatives: ScenarioRuns[]): number {
  const base = asIs?.latest ? runScenarioRef(asIs.latest)?.baseline_revision : undefined;
  if (base === undefined || !asIs?.completed.length) return 1;
  const count = alternatives.filter((alt) => alt.completed.length > 0 && alt.latest && runScenarioRef(alt.latest)?.baseline_revision === base).length;
  return Math.max(1, count);
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
