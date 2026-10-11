/**
 * Il workspace degli scenari dell'hero (SIM-14): AS-IS, A, B con i run veri di
 * `scripts/launch_media_scenarios.py` (3 ripetizioni ciascuno, seed comune).
 *
 * Il primo run dell'AS-IS e del B sono gli stessi run della demo (301 e 302:
 * stesso modello, stesso seed), cosi' heatmap e confronto restano coerenti.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { IDS, simulationRuns } from "./demo";

type ModelResource = { id: string; name: string; cost_per_hour: number; amount: number; calendar_id?: string };
type Model = {
  calendars: { id: string; name: string; periods: { from_day: string; to_day: string; begin: string; end: string }[] }[];
  pools: { resources: ModelResource[] }[];
  activities: { element_id: string; assignments: { resource_id: string; duration: { mean: number } }[] }[];
  gateways: { element_id: string; branches: { flow_id: string; probability: number }[] }[];
};
type ScenarioRun = { seed: number; summary: Record<string, unknown> };
type Scenario = { label: "AS-IS" | "A" | "B"; name: string; model: Model; runs: ScenarioRun[] };

const data = JSON.parse(readFileSync(resolve(__dirname, "data", "scenarios.json"), "utf-8")) as {
  seed: number; total_cases: number; scenarios: Scenario[];
};

const hhmm = (value: string) => value.slice(0, 5);

/** La bozza del pannello Scenario, ricavata dal modello IR simulato. */
function draftOf(model: Model) {
  const resources = model.pools.flatMap((pool) => pool.resources);
  return {
    scenarioName: "Current process",
    totalCases: data.total_cases,
    arrivalIntervalMinutes: 96,
    defaultTaskMinutes: 10,
    resources: resources.map((r) => ({
      id: r.id, name: r.name, costPerHour: r.cost_per_hour, amount: r.amount, parametersConfirmed: true,
      ...(r.calendar_id && r.calendar_id !== "delir-calendar-standard" ? { calendarId: r.calendar_id } : {}),
    })),
    tasks: Object.fromEntries(model.activities.map((a) => [a.element_id, {
      meanMinutes: Math.round(a.assignments[0].duration.mean / 60), distribution: "norm", resourceId: a.assignments[0].resource_id, assignmentSource: "bpmn",
    }])),
    gateways: Object.fromEntries(model.gateways.map((g) => [g.element_id, Object.fromEntries(g.branches.map((b) => [b.flow_id, Math.round(b.probability * 100)]))])),
    calendars: model.calendars
      .filter((c) => c.id !== "delir-calendar-standard")
      .map((c) => ({ id: c.id, name: c.name, periods: c.periods.map((p) => ({ ...p, begin: hhmm(p.begin), end: hhmm(p.end) })) })),
  };
}

type Draft = ReturnType<typeof draftOf>;

/** Le differenze di uno scenario dall'AS-IS, come patch del pannello. */
function patchOf(base: Draft, scenario: Draft) {
  const ops: { op: "set"; path: unknown[]; value: unknown }[] = [];
  const known = new Set(base.calendars.map((c) => c.id));
  scenario.calendars.filter((c) => !known.has(c.id)).forEach((c) => ops.push({ op: "set", path: ["calendars", { id: c.id }], value: c }));
  for (const r of scenario.resources) {
    const before = base.resources.find((b) => b.id === r.id);
    if (before && before.calendarId !== r.calendarId) ops.push({ op: "set", path: ["resources", { id: r.id }, "calendarId"], value: r.calendarId });
  }
  for (const [id, task] of Object.entries(scenario.tasks)) {
    if (base.tasks[id] && base.tasks[id].meanMinutes !== task.meanMinutes) ops.push({ op: "set", path: ["tasks", id, "meanMinutes"], value: task.meanMinutes });
  }
  for (const [id, branches] of Object.entries(scenario.gateways)) {
    for (const [flow, value] of Object.entries(branches)) {
      if (base.gateways[id]?.[flow] !== value) ops.push({ op: "set", path: ["gateways", id, flow], value });
    }
  }
  return ops;
}

const drafts = data.scenarios.map((s) => draftOf(s.model));
const ids = { "AS-IS": 1, A: 2, B: 3 } as const;

export const heroWorkspace = {
  bpmn_model_id: IDS.model,
  seed: data.seed,
  baseline: {
    id: 1, kind: "baseline", label: "AS-IS", name: data.scenarios[0].name, revision: 1, draft: drafts[0], patch: [], conflicts: [],
    created_at: "2026-10-03T09:00:00Z", updated_at: "2026-10-03T09:00:00Z",
  },
  alternatives: data.scenarios.slice(1).map((s, i) => ({
    id: ids[s.label], kind: "alternative", label: s.label, name: s.name, revision: 1,
    draft: drafts[i + 1], patch: patchOf(drafts[0], drafts[i + 1]), conflicts: [],
    created_at: "2026-10-03T09:10:00Z", updated_at: "2026-10-03T09:10:00Z",
  })),
};

/** Run 301 e 302 sono la prima ripetizione di AS-IS e B; gli altri sono nuovi. */
const firstRun: Record<string, number> = { "AS-IS": IDS.asIsRun, B: IDS.toBeRun };
let next = 401;

export const heroRuns = data.scenarios.flatMap((scenario) => scenario.runs.map((run, index) => {
  const reused = index === 0 ? firstRun[scenario.label] : undefined;
  const base = reused ? simulationRuns.find((r) => r.id === reused)! : simulationRuns[0];
  const id = reused ?? next++;
  return {
    ...base,
    id,
    scenario_name: scenario.label === "AS-IS" ? "AS-IS" : `${scenario.label} · ${scenario.name}`,
    request: {
      ...(base.request as Record<string, unknown>),
      seed: run.seed,
      workspace_scenario: { id: ids[scenario.label], revision: 1, baseline_revision: 1 },
      replication_group: `hero-${scenario.label}`,
      replication_index: index + 1,
    },
    summary: run.summary,
    created_at: `2026-10-03T09:${String(20 + id % 40).padStart(2, "0")}:00Z`,
    completed_at: `2026-10-03T09:${String(21 + id % 40).padStart(2, "0")}:00Z`,
  };
}));

/** Il processo compatto dell'hero (scripts/launch_media_hero_process.py) e i suoi due run. */
export const heroXml = readFileSync(resolve(__dirname, "data", "hero.bpmn"), "utf-8");
const heroSim = JSON.parse(readFileSync(resolve(__dirname, "data", "hero-runs.json"), "utf-8")) as Record<"as_is" | "to_be", Record<string, unknown> & { summary: unknown; request: unknown; scenario: unknown; result: unknown; name: string }>;
export const heroApi = JSON.parse(readFileSync(resolve(__dirname, "data", "hero-api.json"), "utf-8")) as { simulation_template: unknown; simulation_provenance: unknown };

export function heroRunData(id: number) {
  if (id === IDS.asIsRun) return heroSim.as_is;
  if (id === IDS.toBeRun) return heroSim.to_be;
  return null;
}

export const heroRunRecords = ([[IDS.toBeRun, heroSim.to_be, "2026-10-03T10:14:00Z"], [IDS.asIsRun, heroSim.as_is, "2026-10-03T09:48:00Z"]] as const).map(([id, run, at]) => ({
  id, bpmn_model_id: IDS.model, process_id: IDS.process, scenario_name: run.name, engine: "prosimos", status: "completed",
  idempotency_key: `hero-${id}`, request: run.request, scenario: run.scenario, result: run.result, outputs: [], summary: run.summary,
  error: null, created_at: at, completed_at: at,
}));

/**
 * La tela di simulazione dell'hero: il processo intero a sinistra e quattro
 * widget KPI del prodotto a destra (tempo medio, coda, throughput, costo), le
 * misure che il consulente guarda durante il replay, come grafici che crescono. Proporzioni ~3,7:1, come
 * una fascia dello schermo diviso.
 */
// Grafici, non numeri: l'andamento si legge anche da lontano.
const kpi = (id: string, kind: "line" | "area", metric: string, title: string, color: string, x: number, y: number, width = 288, height = 252) => ({
  id, title, kind, metric, width: "half", text: "**${metric}**", metricExpression: "", target: 100,
  followFilter: false, activityId: "", showLabels: true, color, canvas: { x, y, width, height },
});
export const heroSimulationLayout = {
  version: 1,
  process: { canvas: { x: 0, y: 0, width: 1300, height: 520 }, groupId: "hero", beforeId: "__first__", width: "full", height: 520 },
  groups: [{
    id: "hero",
    title: "",
    widgets: [
      kpi("hero-cycle", "line", "cycle", "Average cycle time", "violet", 1324, 0),
      kpi("hero-queued", "area", "queued", "Queued cases", "amber", 1636, 0),
      kpi("hero-throughput", "line", "throughput", "Throughput", "blue", 1324, 268),
      kpi("hero-cost", "area", "cost", "Accrued cost", "teal", 1636, 268),
    ],
  }],
};

/** La stessa tela con i quattro grafici sotto il processo: ~16:9, per l'inquadratura singola. */
export const heroSimulationLayoutSolo = {
  ...heroSimulationLayout,
  groups: [{
    id: "hero",
    title: "",
    widgets: [
      kpi("hero-cycle", "line", "cycle", "Average cycle time", "violet", 0, 536, 316, 240),
      kpi("hero-queued", "area", "queued", "Queued cases", "amber", 328, 536, 316, 240),
      kpi("hero-throughput", "line", "throughput", "Throughput", "blue", 656, 536, 316, 240),
      kpi("hero-cost", "area", "cost", "Accrued cost", "teal", 984, 536, 316, 240),
    ],
  }],
};
