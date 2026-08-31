import type {
  CreateSimulationRunInput,
  ScenarioTemplate,
} from "./simulationTypes";

export type ResourceDraft = {
  id: string;
  name: string;
  costPerHour: number;
  amount: number;
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
  tasks: Record<string, TaskDraft>;
  gateways: Record<string, GatewayDraft>;
};

export const DEFAULT_SCENARIO: ScenarioDraft = {
  scenarioName: "Baseline AS-IS",
  totalCases: 100,
  arrivalIntervalMinutes: 30,
  defaultTaskMinutes: 15,
  resources: [{ id: "res-1", name: "Operatore", costPerHour: 35, amount: 1 }],
  tasks: {},
  gateways: {},
};

function isStructured(draft: ScenarioDraft): boolean {
  return (
    draft.resources.length > 1 ||
    Object.keys(draft.tasks).length > 0 ||
    Object.keys(draft.gateways).length > 0
  );
}

export function scenarioToInput(
  draft: ScenarioDraft,
  currentBpmnXml: string | null,
): Omit<CreateSimulationRunInput, "idempotencyKey"> {
  const primary = draft.resources[0] ?? DEFAULT_SCENARIO.resources[0];
  const base = {
    scenarioName: draft.scenarioName,
    totalCases: draft.totalCases,
    currentBpmnXml,
    arrivalIntervalSeconds: Math.max(1, Math.round(draft.arrivalIntervalMinutes * 60)),
    defaultTaskDurationSeconds: Math.max(1, Math.round(draft.defaultTaskMinutes * 60)),
    defaultCostPerHour: primary.costPerHour,
    resourceAmount: primary.amount,
    resourceName: primary.name,
  };

  if (!isStructured(draft)) return base;

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
      resourceId: task.resourceId || primary.id,
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
  const primaryId = draft.resources[0]?.id ?? DEFAULT_SCENARIO.resources[0].id;

  const tasks: Record<string, TaskDraft> = {};
  for (const task of template.tasks) {
    tasks[task.element_id] = draft.tasks[task.element_id] ?? {
      meanMinutes: draft.defaultTaskMinutes,
      distribution: "norm",
      resourceId: primaryId,
    };
    if (!draft.resources.some((r) => r.id === tasks[task.element_id].resourceId)) {
      tasks[task.element_id] = { ...tasks[task.element_id], resourceId: primaryId };
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

  return { ...draft, tasks, gateways };
}

// --- localStorage persistence (best-effort, per bpmn model) ------------------

const KEY = (bpmnModelId: string) => `delir-sim-scenario:${bpmnModelId}`;

export function loadScenarioDraft(bpmnModelId: string): ScenarioDraft {
  try {
    const raw = window.localStorage.getItem(KEY(bpmnModelId));
    if (!raw) return structuredClone(DEFAULT_SCENARIO);
    const parsed = JSON.parse(raw) as Partial<ScenarioDraft>;
    return {
      ...structuredClone(DEFAULT_SCENARIO),
      ...parsed,
      resources:
        Array.isArray(parsed.resources) && parsed.resources.length > 0
          ? parsed.resources
          : structuredClone(DEFAULT_SCENARIO.resources),
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
