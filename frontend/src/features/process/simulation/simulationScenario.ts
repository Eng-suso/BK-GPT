import type {
  CreateSimulationRunInput,
  DistributionName,
  ScenarioTemplate,
  ScenarioTemplateResource,
  SimCalendar,
} from "./simulationTypes";

export type ResourceDraft = {
  id: string;
  name: string;
  costPerHour: number;
  amount: number;
  source?: ScenarioTemplateResource;
  parametersConfirmed?: boolean;
  /** Assente = il calendario standard. */
  calendarId?: string;
};

export type TaskDraft = {
  meanMinutes: number;
  distribution: DistributionName;
  resourceId: string;
  assignmentSource?: "bpmn" | "manual";
  /** Facoltativi: assenti, il backend applica le ipotesi standard. */
  stdMinutes?: number;
  minMinutes?: number;
  maxMinutes?: number;
};

/** Un calendario di lavoro dello scenario, con orari ``HH:MM``. */
export type CalendarDraft = SimCalendar;

/** element_id -> flow_id -> probability (0–100) */
export type GatewayDraft = Record<string, number>;

export type ScenarioDraft = {
  scenarioName: string;
  totalCases: number;
  arrivalIntervalMinutes: number;
  /** fallback duration for tasks without their own config */
  defaultTaskMinutes: number;
  resources: ResourceDraft[];
  excludedResourceIds?: string[];
  tasks: Record<string, TaskDraft>;
  gateways: Record<string, GatewayDraft>;
  calendars?: CalendarDraft[];
};

export const DEFAULT_SCENARIO: ScenarioDraft = {
  scenarioName: "Baseline AS-IS",
  totalCases: 100,
  arrivalIntervalMinutes: 30,
  defaultTaskMinutes: 15,
  resources: [],
  tasks: {},
  gateways: {},
};

export function resourceParametersValid(resource: ResourceDraft): boolean {
  return Boolean(resource.id) && Boolean(resource.name.trim()) && Number.isFinite(resource.costPerHour) &&
    resource.costPerHour >= 0 && Number.isInteger(resource.amount) &&
    resource.amount >= 1 && resource.amount <= 1000;
}

export function scenarioResourceIssues(draft: ScenarioDraft) {
  const missingResources = draft.resources.length === 0;
  const pending = draft.resources.filter((r) => r.parametersConfirmed === false || !resourceParametersValid(r)).length;
  const ids = new Set(draft.resources.map((r) => r.id));
  const unassigned = Object.values(draft.tasks).filter((task) => !ids.has(task.resourceId)).length;
  return { missingResources, pending, unassigned,
    ready: !missingResources && ids.size === draft.resources.length && pending === 0 && unassigned === 0 && Object.keys(draft.tasks).length > 0 };
}

/** Quali parametri della durata ha senso indicare per ogni distribuzione. */
export const DISTRIBUTION_PARAMETERS: Record<DistributionName, { mean: boolean; std: boolean; bounds: boolean }> = {
  fixed: { mean: true, std: false, bounds: false },
  expon: { mean: true, std: false, bounds: true },
  uniform: { mean: false, std: false, bounds: true },
  norm: { mean: true, std: true, bounds: true },
  lognorm: { mean: true, std: true, bounds: true },
  gamma: { mean: true, std: true, bounds: true },
};

export type TaskDurationIssue = "uniformBounds" | "boundsOrder";

/** Cosa manca alla durata per costruire la richiesta; il resto lo valida il backend. */
export function taskDurationIssue(task: TaskDraft): TaskDurationIssue | null {
  if (!DISTRIBUTION_PARAMETERS[task.distribution].bounds) return null;
  if (task.distribution === "uniform" && (task.minMinutes === undefined || task.maxMinutes === undefined)) {
    return "uniformBounds";
  }
  if (task.minMinutes !== undefined && task.maxMinutes !== undefined && task.minMinutes >= task.maxMinutes) {
    return "boundsOrder";
  }
  return null;
}

export type CalendarIssue = "name" | "periods" | "periodOrder";

export function calendarIssue(calendar: CalendarDraft): CalendarIssue | null {
  if (!calendar.name.trim()) return "name";
  if (calendar.periods.length === 0) return "periods";
  // Un periodo che passa la mezzanotte va diviso in due.
  if (calendar.periods.some((period) => !period.begin || !period.end || period.begin >= period.end)) return "periodOrder";
  return null;
}

export function scenarioParameterIssues(draft: ScenarioDraft) {
  const durations = Object.values(draft.tasks).filter((task) => taskDurationIssue(task) !== null).length;
  const calendars = (draft.calendars ?? []).filter((calendar) => calendarIssue(calendar) !== null).length;
  return { durations, calendars, ready: durations === 0 && calendars === 0 };
}

export function newCalendarId(existing: CalendarDraft[]): string {
  let n = existing.length + 1;
  while (existing.some((c) => c.id === `cal-${n}`)) n += 1;
  return `cal-${n}`;
}

const seconds = (minutes: number | undefined) =>
  minutes === undefined ? undefined : Math.max(0, Math.round(minutes * 60));

function taskMeanSeconds(task: TaskDraft): number {
  const minutes = task.distribution === "uniform" && task.minMinutes !== undefined && task.maxMinutes !== undefined
    ? (task.minMinutes + task.maxMinutes) / 2
    : task.meanMinutes;
  return Math.max(1, Math.round(minutes * 60));
}

export function scenarioToInput(
  draft: ScenarioDraft,
  currentBpmnXml: string | null,
): Omit<CreateSimulationRunInput, "idempotencyKey"> {
  const primary = draft.resources[0];
  const calendarIds = new Set((draft.calendars ?? []).map((c) => c.id));
  const base = {
    scenarioName: draft.scenarioName,
    totalCases: draft.totalCases,
    currentBpmnXml,
    arrivalIntervalSeconds: Math.max(1, Math.round(draft.arrivalIntervalMinutes * 60)),
    defaultTaskDurationSeconds: Math.max(1, Math.round(draft.defaultTaskMinutes * 60)),
    defaultCostPerHour: primary?.costPerHour ?? 0,
    resourceAmount: primary?.amount ?? 1,
    resourceName: primary?.name ?? "",
  };

  return {
    ...base,
    resources: draft.resources.map((r) => ({
      id: r.id,
      name: r.name,
      costPerHour: r.costPerHour,
      amount: r.amount,
      calendarId: calendarIds.has(r.calendarId ?? "") ? r.calendarId : undefined,
    })),
    tasks: Object.entries(draft.tasks).map(([elementId, task]) => {
      const parameters = DISTRIBUTION_PARAMETERS[task.distribution];
      return {
        elementId,
        meanSeconds: taskMeanSeconds(task),
        distribution: task.distribution,
        resourceId: task.resourceId,
        stdSeconds: parameters.std && task.stdMinutes !== undefined ? Math.max(1, Math.round(task.stdMinutes * 60)) : undefined,
        minSeconds: parameters.bounds ? seconds(task.minMinutes) : undefined,
        maxSeconds: parameters.bounds ? seconds(task.maxMinutes) : undefined,
      };
    }),
    calendars: draft.calendars ?? [],
    gateways: Object.entries(draft.gateways).map(([elementId, branches]) => ({
      elementId,
      branches: Object.entries(branches).map(([flowId, probability]) => ({
        flowId,
        probability: Math.max(0, Math.min(1, probability / 100)),
      })),
    })),
  };
}

/** Fill in defaults for template elements, drop stale ones. */
export function seedDraftFromTemplate(
  draft: ScenarioDraft,
  template: ScenarioTemplate,
): ScenarioDraft {
  const candidates = template.resources ?? [];
  // Model membership is evidence, never evidence of staffing or hourly rates.
  const resources = draft.resources.map((r) => {
    const source = candidates.find((candidate) => candidate.id === r.id);
    return source ? { ...r, source, name: r.name === r.source?.name ? source.name : r.name } : r.source ? { ...r, source: undefined, parametersConfirmed: false } : r;
  });
  for (const source of candidates) {
    if (!resources.some((r) => r.id === source.id) && !draft.excludedResourceIds?.includes(source.id)) {
      resources.push({ id: source.id, name: source.name, costPerHour: 0, amount: 1,
        source, parametersConfirmed: false });
    }
  }

  const tasks: Record<string, TaskDraft> = {};
  for (const task of template.tasks) {
    const modelResourceId = candidates.find((r) => r.task_ids.includes(task.element_id) && resources.some((resource) => resource.id === r.id))?.id ?? "";
    const existing = draft.tasks[task.element_id];
    const cfg = existing ?? {
      meanMinutes: draft.defaultTaskMinutes,
      distribution: "norm" as const,
      resourceId: modelResourceId,
      assignmentSource: "bpmn" as const,
    };
    if (cfg.assignmentSource === "bpmn") {
      tasks[task.element_id] = { ...cfg, resourceId: modelResourceId };
    } else if (cfg.resourceId && !resources.some((r) => r.id === cfg.resourceId)) {
      tasks[task.element_id] = { ...cfg, resourceId: modelResourceId, assignmentSource: "bpmn" };
    } else {
      tasks[task.element_id] = cfg;
    }
  }

  const gateways: Record<string, GatewayDraft> = {};
  for (const gateway of template.gateways) {
    const existing = draft.gateways[gateway.element_id];
    const flows = gateway.branches.map((b) => b.flow_id);
    if (existing && flows.every((f) => f in existing)) {
      gateways[gateway.element_id] = Object.fromEntries(
        flows.map((f) => [f, existing[f]]),
      );
    } else {
      const even = Math.round((100 / flows.length) * 10) / 10;
      gateways[gateway.element_id] = Object.fromEntries(
        flows.map((f, i) => [
          f,
          i === flows.length - 1 ? 100 - even * (flows.length - 1) : even,
        ]),
      );
    }
  }

  return { ...draft, resources, tasks, gateways };
}

// --- localStorage persistence (best-effort, per bpmn model) ------------------

const KEY = (bpmnModelId: string) => `delir-sim-scenario:${bpmnModelId}`;

export function loadScenarioDraft(bpmnModelId: string): ScenarioDraft {
  try {
    const raw = window.localStorage.getItem(KEY(bpmnModelId));
    if (!raw) return structuredClone(DEFAULT_SCENARIO);
    const parsed = JSON.parse(raw) as Partial<ScenarioDraft>;
    const resources = Array.isArray(parsed.resources) ? parsed.resources : [];
    // Migrate the old untouched, generated operator; retain explicit custom roles.
    const legacyDefault = (resource: ResourceDraft) => resource.id === "res-1" &&
      resource.name === "Operatore" && resource.amount === 1 && resource.costPerHour === 35 &&
      resource.parametersConfirmed === undefined && !resource.source;
    const migratedResources = resources.filter((r) => !legacyDefault(r)).map((r) => ({
      ...r, parametersConfirmed: r.parametersConfirmed ?? false,
    }));
    return {
      ...structuredClone(DEFAULT_SCENARIO),
      ...parsed,
      resources: migratedResources,
      tasks: parsed.tasks ?? {},
      gateways: parsed.gateways ?? {},
      calendars: Array.isArray(parsed.calendars) ? parsed.calendars : [],
    };
  } catch {
    return structuredClone(DEFAULT_SCENARIO);
  }
}

export function saveScenarioDraft(bpmnModelId: string, draft: ScenarioDraft): void {
  try {
    window.localStorage.setItem(KEY(bpmnModelId), JSON.stringify(draft));
  } catch {
    /* storage unavailable / quota — the draft still lives in component state */
  }
}

export function newResourceId(existing: ResourceDraft[]): string {
  let n = existing.length + 1;
  while (existing.some((r) => r.id === `res-${n}`)) n += 1;
  return `res-${n}`;
}
