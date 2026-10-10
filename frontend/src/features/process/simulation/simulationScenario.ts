import {
  sanitizeAttributes,
  sanitizeGatewayRules,
  sanitizePriorities,
  toModelPatch,
  type BranchRuleDraft,
  type CaseAttributeDraft,
  type GatewayRulesDraft,
} from "./caseRules";
import {
  simCalendarSchema,
  type CreateSimulationRunInput,
  type DistributionName,
  type ScenarioTemplate,
  type ScenarioTemplateResource,
  type SimCalendar,
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

/** La durata di un'attività per un ruolo, in minuti. */
export type DurationDraft = {
  meanMinutes: number;
  distribution: DistributionName;
  /** Facoltativi: assenti, il backend applica le ipotesi standard. */
  stdMinutes?: number;
  minMinutes?: number;
  maxMinutes?: number;
};

/** Un altro ruolo che può svolgere l'attività, con la sua durata (A2-2). */
export type AssignmentDraft = DurationDraft & { resourceId: string };

export type TaskDraft = DurationDraft & {
  resourceId: string;
  assignmentSource?: "bpmn" | "manual";
  /** Gli altri ruoli: il motore dà il caso al primo libero. */
  otherAssignments?: AssignmentDraft[];
  /** Le affermazioni dei file collegate come fonte della durata (SIM-07). */
  claims?: { claimId: number; label: string }[];
};

/** Un calendario di lavoro dello scenario, con orari ``HH:MM``. */
export type CalendarDraft = SimCalendar;

/** element_id -> flow_id -> probability (0–100) */
export type GatewayDraft = Record<string, number>;

/** Come arrivano i casi (A2-3): la media fra due arrivi e' ``arrivalIntervalMinutes``. */
export type ArrivalDraft = Omit<DurationDraft, "meanMinutes"> & {
  /** Assente = il calendario standard. */
  calendarId?: string;
};

export type ScenarioDraft = {
  scenarioName: string;
  totalCases: number;
  arrivalIntervalMinutes: number;
  arrival?: ArrivalDraft;
  /** fallback duration for tasks without their own config */
  defaultTaskMinutes: number;
  resources: ResourceDraft[];
  excludedResourceIds?: string[];
  tasks: Record<string, TaskDraft>;
  gateways: Record<string, GatewayDraft>;
  calendars?: CalendarDraft[];
  /** Attributi che ogni caso riceve all'arrivo (A2-1). */
  caseAttributes?: CaseAttributeDraft[];
  /** Decisioni instradate per regola: element_id -> flow_id -> gruppi di condizioni. */
  gatewayRules?: Record<string, GatewayRulesDraft>;
  /** SIM-12: chi passa prima in coda. Indice 0 = priorita' 1, servita per prima. */
  casePriorities?: BranchRuleDraft[];
  /** Proposte di fonti scartate dal consulente: element_id -> id delle affermazioni. */
  dismissedClaims?: Record<string, number[]>;
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

export type TaskDurationIssue = "uniformBounds" | "boundsOrder" | "meanOutsideBounds";

/** Minuti in secondi interi, come arrivano al backend. */
const seconds = (minutes: number | undefined) =>
  minutes === undefined ? undefined : Math.max(0, Math.round(minutes * 60));

/** Cosa manca alla durata per costruire la richiesta; il resto lo valida il backend. */
export function taskDurationIssue(task: DurationDraft): TaskDurationIssue | null {
  if (!DISTRIBUTION_PARAMETERS[task.distribution].bounds) return null;
  if (task.distribution === "uniform" && (task.minMinutes === undefined || task.maxMinutes === undefined)) {
    return "uniformBounds";
  }
  // Confronto sui secondi inviati: 1,001 e 1,002 minuti diventano entrambi 60 s.
  const minimum = seconds(task.minMinutes);
  const maximum = seconds(task.maxMinutes);
  if (minimum !== undefined && maximum !== undefined && minimum >= maximum) return "boundsOrder";
  // Le regole del backend: l'esponenziale vuole la media strettamente dentro i limiti,
  // la normale anche sui limiti. Lognormale e gamma non la vincolano.
  const mean = Math.max(1, Math.round(task.meanMinutes * 60));
  if (task.distribution === "expon" && ((minimum !== undefined && mean <= minimum) || (maximum !== undefined && mean >= maximum))) {
    return "meanOutsideBounds";
  }
  if (task.distribution === "norm" && ((minimum !== undefined && mean < minimum) || (maximum !== undefined && mean > maximum))) {
    return "meanOutsideBounds";
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
  const durations = Object.values(draft.tasks).filter((task) =>
    [task, ...(task.otherAssignments ?? [])].some((duration) => taskDurationIssue(duration) !== null)).length;
  const calendars = (draft.calendars ?? []).filter((calendar) => calendarIssue(calendar) !== null).length;
  const arrival = taskDurationIssue(arrivalDuration(draft)) !== null;
  return { durations, calendars, arrival, ready: durations === 0 && calendars === 0 && !arrival };
}

/** Gli arrivi come una durata: la stessa forma, gli stessi controlli, gli stessi campi. */
export function arrivalDuration(draft: ScenarioDraft): DurationDraft {
  const arrival = draft.arrival;
  return {
    meanMinutes: draft.arrivalIntervalMinutes,
    distribution: arrival?.distribution ?? "expon",
    stdMinutes: arrival?.stdMinutes,
    minMinutes: arrival?.minMinutes,
    maxMinutes: arrival?.maxMinutes,
  };
}

/** Aggiorna gli arrivi della bozza da una durata modificata nel pannello. */
/**
 * Aggiorna gli arrivi della bozza. Senza terzo argomento il calendario resta quello
 * di prima; con ``undefined`` esplicito torna il calendario standard.
 */
export function withArrival(draft: ScenarioDraft, next: DurationDraft, ...calendar: [calendarId: string | undefined] | []): ScenarioDraft {
  const { meanMinutes, ...rest } = next;
  const calendarId = calendar.length ? calendar[0] : draft.arrival?.calendarId;
  return { ...draft, arrivalIntervalMinutes: meanMinutes, arrival: { ...rest, calendarId } };
}

export function newCalendarId(existing: CalendarDraft[]): string {
  let n = existing.length + 1;
  while (existing.some((c) => c.id === `cal-${n}`)) n += 1;
  return `cal-${n}`;
}

/** Il nome del ruolo come lo mostra il pannello: per una lane anche la pool. */
export function roleLabel(resource: ResourceDraft): string {
  return resource.source?.pool_name && resource.source.kind === "lane" ? `${resource.source.pool_name} / ${resource.name}` : resource.name;
}

/** I ruoli dell'attività, il principale per primo. */
export function taskResourceIds(task: TaskDraft): string[] {
  return [task.resourceId, ...(task.otherAssignments ?? []).map((a) => a.resourceId)];
}

/**
 * Tiene solo gli altri ruoli che esistono ancora e che non ripetono un ruolo già
 * presente: un ruolo tolto dalle risorse, o diventato il principale, sparisce.
 */
export function withValidOtherAssignments(task: TaskDraft, resourceIds: ReadonlySet<string>): TaskDraft {
  if (task.otherAssignments === undefined) return task;
  // Una bozza salvata a mano o da una versione vecchia non deve rompere il pannello.
  if (!Array.isArray(task.otherAssignments)) return { ...task, otherAssignments: undefined };
  const seen = new Set([task.resourceId]);
  const kept = task.otherAssignments.filter((a) => {
    if (!a || typeof a !== "object" || !resourceIds.has(a.resourceId) || seen.has(a.resourceId)) return false;
    seen.add(a.resourceId);
    return true;
  });
  return kept.length === task.otherAssignments.length ? task : { ...task, otherAssignments: kept };
}

/** Un altro ruolo per l'attività: il primo non ancora usato, con la stessa durata come punto di partenza. */
export function newOtherAssignment(task: TaskDraft, resources: ResourceDraft[]): AssignmentDraft | null {
  const used = new Set(taskResourceIds(task));
  const free = resources.find((r) => !used.has(r.id));
  if (!free) return null;
  const { meanMinutes, distribution, stdMinutes, minMinutes, maxMinutes } = task;
  return { resourceId: free.id, meanMinutes, distribution, stdMinutes, minMinutes, maxMinutes };
}

function taskMeanSeconds(task: DurationDraft): number {
  const minutes = task.distribution === "uniform" && task.minMinutes !== undefined && task.maxMinutes !== undefined
    ? (task.minMinutes + task.maxMinutes) / 2
    : task.meanMinutes;
  return Math.max(1, Math.round(minutes * 60));
}

function durationInput(duration: DurationDraft) {
  const parameters = DISTRIBUTION_PARAMETERS[duration.distribution];
  return {
    meanSeconds: taskMeanSeconds(duration),
    distribution: duration.distribution,
    stdSeconds: parameters.std && duration.stdMinutes !== undefined ? Math.max(1, Math.round(duration.stdMinutes * 60)) : undefined,
    minSeconds: parameters.bounds ? seconds(duration.minMinutes) : undefined,
    maxSeconds: parameters.bounds ? seconds(duration.maxMinutes) : undefined,
  };
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

  const arrivalCalendar = draft.arrival?.calendarId;
  return {
    ...base,
    arrival: {
      ...durationInput(arrivalDuration(draft)),
      calendarId: arrivalCalendar && calendarIds.has(arrivalCalendar) ? arrivalCalendar : undefined,
    },
    resources: draft.resources.map((r) => ({
      id: r.id,
      name: r.name,
      costPerHour: r.costPerHour,
      amount: r.amount,
      calendarId: calendarIds.has(r.calendarId ?? "") ? r.calendarId : undefined,
    })),
    tasks: Object.entries(draft.tasks).map(([elementId, task]) => {
      const others = task.otherAssignments ?? [];
      return {
        elementId,
        ...durationInput(task),
        resourceId: task.resourceId,
        ...(task.claims?.length ? { claims: task.claims } : {}),
        ...(others.length ? { otherAssignments: others.map((a) => ({ resourceId: a.resourceId, ...durationInput(a) })) } : {}),
      };
    }),
    calendars: draft.calendars ?? [],
    modelPatch: toModelPatch(draft.caseAttributes ?? [], draft.gatewayRules ?? {}, draft.casePriorities ?? []),
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
  const resourceIds = new Set(resources.map((r) => r.id));
  for (const task of template.tasks) {
    const modelResourceId = candidates.find((r) => r.task_ids.includes(task.element_id) && resources.some((resource) => resource.id === r.id))?.id ?? "";
    const existing = draft.tasks[task.element_id];
    const cfg = existing ?? {
      meanMinutes: draft.defaultTaskMinutes,
      distribution: "norm" as const,
      resourceId: modelResourceId,
      assignmentSource: "bpmn" as const,
    };
    let next: TaskDraft = cfg;
    if (cfg.assignmentSource === "bpmn") {
      next = { ...cfg, resourceId: modelResourceId };
    } else if (cfg.resourceId && !resources.some((r) => r.id === cfg.resourceId)) {
      next = { ...cfg, resourceId: modelResourceId, assignmentSource: "bpmn" };
    }
    tasks[task.element_id] = withValidOtherAssignments(next, resourceIds);
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

  // Una decisione per regola resta solo se il BPMN ha ancora la stessa decisione con le stesse uscite.
  const gatewayRules: Record<string, GatewayRulesDraft> = {};
  for (const gateway of template.gateways) {
    const rules = draft.gatewayRules?.[gateway.element_id];
    const flows = gateway.branches.map((b) => b.flow_id);
    if (rules && flows.length === Object.keys(rules).length && flows.every((f) => f in rules)) gatewayRules[gateway.element_id] = rules;
  }

  return { ...draft, resources, tasks, gateways, gatewayRules };
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
      // Una bozza vecchia o modificata a mano non deve rompere il pannello.
      calendars: Array.isArray(parsed.calendars)
        ? parsed.calendars.filter((c) => simCalendarSchema.safeParse(c).success)
        : [],
      caseAttributes: sanitizeAttributes(parsed.caseAttributes),
      arrival: sanitizeArrival(parsed.arrival),
      gatewayRules: sanitizeGatewayRules(parsed.gatewayRules),
      casePriorities: sanitizePriorities(parsed.casePriorities),
    };
  } catch {
    return structuredClone(DEFAULT_SCENARIO);
  }
}

function sanitizeArrival(raw: unknown): ArrivalDraft | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const value = raw as Partial<ArrivalDraft>;
  if (!value.distribution || !(value.distribution in DISTRIBUTION_PARAMETERS)) return undefined;
  const number = (n: unknown) => (typeof n === "number" && Number.isFinite(n) ? n : undefined);
  return {
    distribution: value.distribution,
    stdMinutes: number(value.stdMinutes),
    minMinutes: number(value.minMinutes),
    maxMinutes: number(value.maxMinutes),
    calendarId: typeof value.calendarId === "string" ? value.calendarId : undefined,
  };
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
