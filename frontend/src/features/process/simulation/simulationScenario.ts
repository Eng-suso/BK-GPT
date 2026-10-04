import type {
  CreateSimulationRunInput,
  ScenarioTemplate,
  ScenarioTemplateResource,
} from "./simulationTypes";

export type ResourceDraft = {
  id: string;
  name: string;
  costPerHour: number;
  amount: number;
  source?: ScenarioTemplateResource;
  parametersConfirmed?: boolean;
};

export type TaskDraft = {
  meanMinutes: number;
  distribution: "norm" | "expon" | "fixed";
  resourceId: string;
};

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
  return Boolean(resource.name.trim()) && Number.isFinite(resource.costPerHour) &&
    resource.costPerHour >= 0 && Number.isInteger(resource.amount) &&
    resource.amount >= 1 && resource.amount <= 1000;
}

export function scenarioResourceIssues(draft: ScenarioDraft) {
  const missingResources = draft.resources.length === 0;
  const pending = draft.resources.filter((r) => r.parametersConfirmed === false || !resourceParametersValid(r)).length;
  const ids = new Set(draft.resources.map((r) => r.id));
  const unassigned = Object.values(draft.tasks).filter((task) => !ids.has(task.resourceId)).length;
  return { missingResources, pending, unassigned,
    ready: !missingResources && pending === 0 && unassigned === 0 && Object.keys(draft.tasks).length > 0 };
}

export function scenarioToInput(
  draft: ScenarioDraft,
  currentBpmnXml: string | null,
): Omit<CreateSimulationRunInput, "idempotencyKey"> {
  const primary = draft.resources[0];
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
    })),
    tasks: Object.entries(draft.tasks).map(([elementId, task]) => ({
      elementId,
      meanSeconds: Math.max(1, Math.round(task.meanMinutes * 60)),
      distribution: task.distribution,
      resourceId: task.resourceId,
    })),
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
    return source ? { ...r, source, name: r.name === r.source?.name ? source.name : r.name } : r;
  });
  for (const source of candidates) {
    if (!resources.some((r) => r.id === source.id) && !draft.excludedResourceIds?.includes(source.id)) {
      resources.push({ id: source.id, name: source.name, costPerHour: 0, amount: 1,
        source, parametersConfirmed: false });
    }
  }

  const tasks: Record<string, TaskDraft> = {};
  for (const task of template.tasks) {
    tasks[task.element_id] = draft.tasks[task.element_id] ?? {
      meanMinutes: draft.defaultTaskMinutes,
      distribution: "norm",
      resourceId: candidates.find((r) => r.task_ids.includes(task.element_id) && resources.some((resource) => resource.id === r.id))?.id ?? "",
    };
    if (!resources.some((r) => r.id === tasks[task.element_id].resourceId)) {
      tasks[task.element_id] = { ...tasks[task.element_id], resourceId:
        tasks[task.element_id].resourceId ? candidates.find((r) => r.task_ids.includes(task.element_id) && resources.some((resource) => resource.id === r.id))?.id ?? "" : "" };
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
    const legacy = resources.length === 1 && resources[0].id === "res-1" &&
      resources[0].name === "Operatore" && resources[0].amount === 1 &&
      resources[0].costPerHour === 35 && resources[0].parametersConfirmed === undefined && !resources[0].source;
    return {
      ...structuredClone(DEFAULT_SCENARIO),
      ...parsed,
      resources: legacy ? [] : resources,
      tasks: parsed.tasks ?? {},
      gateways: parsed.gateways ?? {},
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
