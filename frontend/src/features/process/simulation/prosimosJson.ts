import { DEFAULT_SCENARIO, type DurationDraft, type ScenarioDraft } from "./simulationScenario";
import type { DistributionName, ScenarioTemplate, SimCalendar } from "./simulationTypes";

type JsonObject = Record<string, unknown>;
export type ProsimosIdMapping = {
  tasks?: Record<string, string>;
  gateways?: Record<string, string>;
  flows?: Record<string, string>;
  waits?: Record<string, string>;
};
export const flowMappingKey = (gatewayId: string, flowId: string): string => `${gatewayId}::${flowId}`;
const KNOWN_SECTIONS = new Set([
  "resource_profiles", "arrival_time_distribution", "arrival_time_calendar",
  "gateway_branching_probabilities", "task_resource_distribution", "resource_calendars",
  "batch_processing", "case_attributes", "event_distribution",
]);
const DISTRIBUTIONS: Record<string, DistributionName> = {
  fix: "fixed", fixed: "fixed", expon: "expon", uniform: "uniform",
  norm: "norm", lognorm: "lognorm", gamma: "gamma",
};

function object(value: unknown, path: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${path}: oggetto richiesto.`);
  return value as JsonObject;
}
function list(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${path}: elenco richiesto.`);
  return value;
}
function string(value: unknown, path: string): string {
  if (typeof value !== "string" || !value) throw new Error(`${path}: testo richiesto.`);
  return value;
}
function number(value: unknown, path: string): number {
  const result = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : NaN;
  if (!Number.isFinite(result)) throw new Error(`${path}: numero non valido.`);
  return result;
}
function keys(value: JsonObject, allowed: readonly string[], path: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length) throw new Error(`${path}: campi non mappati (${unknown.join(", ")}).`);
}
function duration(value: unknown, path: string): DurationDraft {
  const distribution = object(value, path);
  keys(distribution, ["distribution_name", "distribution_params"], path);
  const rawName = string(distribution.distribution_name, `${path}.distribution_name`);
  const name = DISTRIBUTIONS[rawName];
  if (!name) throw new Error(`${path}: distribuzione ${rawName} non supportata dall'editor.`);
  const params = list(distribution.distribution_params, `${path}.distribution_params`).map((entry, index) => {
    const row = object(entry, `${path}.distribution_params[${index}]`);
    keys(row, ["value"], `${path}.distribution_params[${index}]`);
    return number(row.value, `${path}.distribution_params[${index}].value`);
  });
  const count = name === "fixed" ? 1 : name === "uniform" ? 2 : name === "expon" ? 3 : 4;
  if (params.length !== count) throw new Error(`${path}: ${name} richiede ${count} parametri, trovati ${params.length}.`);
  if (name === "uniform") return { distribution: name, meanMinutes: (params[0] + params[1]) / 120, minMinutes: params[0] / 60, maxMinutes: params[1] / 60 };
  if (name === "fixed") return { distribution: name, meanMinutes: params[0] / 60 };
  if (name === "expon") return { distribution: name, meanMinutes: params[0] / 60, minMinutes: params[1] / 60, maxMinutes: params[2] / 60 };
  return {
    distribution: name, meanMinutes: params[0] / 60,
    stdMinutes: (name === "norm" ? params[1] : Math.sqrt(params[1])) / 60,
    minMinutes: params[2] / 60, maxMinutes: params[3] / 60,
  };
}

function period(value: unknown, path: string): SimCalendar["periods"][number] {
  const row = object(value, path);
  keys(row, ["from", "to", "beginTime", "endTime"], path);
  const from_day = string(row.from, `${path}.from`);
  const to_day = string(row.to, `${path}.to`);
  if (!/^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)$/.test(from_day) ||
    !/^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)$/.test(to_day)) throw new Error(`${path}: giorno non valido.`);
  const begin = string(row.beginTime, `${path}.beginTime`);
  const end = string(row.endTime, `${path}.endTime`);
  const validTime = (time: string) => /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,3})?)?$/.test(time);
  if (!validTime(begin) || !validTime(end)) throw new Error(`${path}: orario non valido.`);
  return { from_day: from_day as SimCalendar["periods"][number]["from_day"], to_day: to_day as SimCalendar["periods"][number]["to_day"], begin, end };
}

/** Convert the six core Prosimos sections only when every nonempty section is representable. */
export function importProsimosJson(value: JsonObject, current: ScenarioDraft | null, template: ScenarioTemplate | null, mapping: ProsimosIdMapping = {}): ScenarioDraft {
  if (!template) throw new Error("Il modello BPMN deve essere caricato prima di importare un JSON Prosimos.");
  const extra = Object.entries(value).filter(([key, item]) => !KNOWN_SECTIONS.has(key) && item != null && (!Array.isArray(item) || item.length > 0));
  for (const key of ["batch_processing", "case_attributes"]) {
    if (value[key] !== undefined) list(value[key], key);
  }
  const advanced = ["batch_processing", "case_attributes"].filter((key) => Array.isArray(value[key]) && (value[key] as unknown[]).length > 0);
  if (extra.length || advanced.length) throw new Error(`Sezioni da mappare prima dell'importazione: ${[...advanced, ...extra.map(([key]) => key)].join(", ")}.`);
  const base = current ?? DEFAULT_SCENARIO;
  const calendars = list(value.resource_calendars, "resource_calendars").map((entry, index) => {
    const row = object(entry, `resource_calendars[${index}]`);
    keys(row, ["id", "name", "time_periods"], `resource_calendars[${index}]`);
    return { id: string(row.id, "calendar.id"), name: string(row.name, "calendar.name"), periods: list(row.time_periods, "calendar.time_periods").map((item, i) => period(item, `calendar.periods[${i}]`)) };
  });
  const standardId = template.standard_calendar?.id;
  const customCalendars = calendars.filter((calendar) => calendar.id !== standardId);
  const profiles = list(value.resource_profiles, "resource_profiles");
  if (!profiles.length) throw new Error("resource_profiles: almeno un profilo risorsa richiesto.");
  const resourceRows = profiles.flatMap((entry, profileIndex) => {
    const path = `resource_profiles[${profileIndex}]`;
    const profile = object(entry, path);
    keys(profile, ["id", "name", "resource_list"], path);
    string(profile.id, `${path}.id`);
    string(profile.name, `${path}.name`);
    return list(profile.resource_list, `${path}.resource_list`).map((item, index) => {
      const resourcePath = `${path}.resource_list[${index}]`;
      const row = object(item, resourcePath);
      keys(row, ["id", "name", "cost_per_hour", "amount", "calendar", "assignedTasks"], resourcePath);
      return row;
    });
  });
  const resources = resourceRows.map((row) => {
    const calendarId = row.calendar == null ? undefined : string(row.calendar, "resource.calendar");
    if (calendarId && calendarId !== standardId && !customCalendars.some((calendar) => calendar.id === calendarId)) throw new Error(`Calendario risorsa non trovato: ${calendarId}.`);
    return { id: string(row.id, "resource.id"), name: string(row.name, "resource.name"), costPerHour: number(row.cost_per_hour, "resource.cost_per_hour"), amount: number(row.amount, "resource.amount"), parametersConfirmed: true, ...(calendarId && calendarId !== standardId ? { calendarId } : {}) };
  });
  const resourceIds = new Set(resources.map((resource) => resource.id));
  if (resourceIds.size !== resources.length) throw new Error("Identificativi risorsa duplicati tra i profili: assegnazione ambigua.");
  const taskIds = new Set(template.tasks.map((task) => task.element_id));
  const tasks: ScenarioDraft["tasks"] = {};
  for (const [index, item] of list(value.task_resource_distribution, "task_resource_distribution").entries()) {
    const row = object(item, `task_resource_distribution[${index}]`);
    keys(row, ["task_id", "resources"], `task_resource_distribution[${index}]`);
    const sourceId = string(row.task_id, "task_id");
    const id = mapping.tasks?.[sourceId] || sourceId;
    if (!taskIds.has(id)) throw new Error(`Attività non presente nel BPMN: ${id}.`);
    if (tasks[id]) throw new Error(`Attività ${id} assegnata da più elementi del JSON.`);
    const assignments = list(row.resources, `${id}.resources`).map((entry, i) => {
      const assignment = object(entry, `${id}.resources[${i}]`);
      keys(assignment, ["resource_id", "distribution_name", "distribution_params"], `${id}.resources[${i}]`);
      const resourceId = string(assignment.resource_id, "resource_id");
      if (!resourceIds.has(resourceId)) throw new Error(`Risorsa non trovata per ${id}: ${resourceId}.`);
      return { resourceId, ...duration({ distribution_name: assignment.distribution_name, distribution_params: assignment.distribution_params }, `${id}.resources[${i}]`) };
    });
    if (!assignments.length) throw new Error(`${id}: nessuna risorsa assegnata.`);
    const [primary, ...otherAssignments] = assignments;
    tasks[id] = { ...primary, assignmentSource: "manual", ...(otherAssignments.length ? { otherAssignments } : {}) };
  }
  const missingTasks = [...taskIds].filter((id) => !tasks[id]);
  if (missingTasks.length) throw new Error(`Attività senza durata nel JSON: ${missingTasks.join(", ")}.`);
  const gatewayIds = new Map(template.gateways.map((gateway) => [gateway.element_id, new Set(gateway.branches.map((branch) => branch.flow_id))]));
  const gateways: ScenarioDraft["gateways"] = {};
  for (const [index, item] of list(value.gateway_branching_probabilities, "gateway_branching_probabilities").entries()) {
    const row = object(item, `gateway_branching_probabilities[${index}]`);
    keys(row, ["gateway_id", "probabilities"], `gateway_branching_probabilities[${index}]`);
    const sourceId = string(row.gateway_id, "gateway_id");
    const id = mapping.gateways?.[sourceId] || sourceId;
    const flows = gatewayIds.get(id);
    if (!flows) throw new Error(`Decisione non presente nel BPMN: ${id}.`);
    if (gateways[id]) throw new Error(`Decisione ${id} assegnata da più elementi del JSON.`);
    gateways[id] = {};
    for (const branch of list(row.probabilities, `${id}.probabilities`)) {
      const probability = object(branch, `${id}.probabilities`);
      keys(probability, ["path_id", "value"], `${id}.probabilities`);
      const sourceFlowId = string(probability.path_id, "path_id");
      const flowId = mapping.flows?.[flowMappingKey(sourceId, sourceFlowId)] || sourceFlowId;
      if (!flows.has(flowId)) throw new Error(`Flusso non presente nel BPMN: ${flowId}.`);
      if (flowId in gateways[id]) throw new Error(`Flusso ${flowId} assegnato da più percorsi del JSON.`);
      gateways[id][flowId] = number(probability.value, "probability") * 100;
    }
    const missingFlows = [...flows].filter((flowId) => !(flowId in gateways[id]));
    if (missingFlows.length) throw new Error(`Flussi senza probabilità per ${id}: ${missingFlows.join(", ")}.`);
    if (Math.abs(Object.values(gateways[id]).reduce((sum, probability) => sum + probability, 0) - 100) > 0.001) throw new Error(`Le probabilità di ${id} devono sommare a 1.`);
  }
  const arrival = duration(value.arrival_time_distribution, "arrival_time_distribution");
  const templateWaits = new Map((template.waits ?? []).map((wait) => [wait.element_id, wait]));
  const waits: NonNullable<ScenarioDraft["waits"]> = {};
  const seenWaits = new Set<string>();
  for (const [index, item] of list(value.event_distribution ?? [], "event_distribution").entries()) {
    const path = `event_distribution[${index}]`;
    const row = object(item, path);
    keys(row, ["event_id", "distribution_name", "distribution_params"], path);
    const sourceId = string(row.event_id, `${path}.event_id`);
    const id = mapping.waits?.[sourceId] || sourceId;
    const templateWait = templateWaits.get(id);
    if (!templateWait) throw new Error(`${path}: evento ${id} non presente tra le attese del BPMN corrente.`);
    if (seenWaits.has(id)) throw new Error(`${path}: evento ${id} duplicato.`);
    seenWaits.add(id);
    const parsed = duration({ distribution_name: row.distribution_name, distribution_params: row.distribution_params }, path);
    // Prosimos represents an unset message/signal wait as a fixed zero duration.
    if (parsed.distribution === "fixed" && parsed.meanMinutes === 0) {
      if (templateWait.kind === "timer") throw new Error(`${path}: il timer ${id} ha durata zero; non può sostituire la durata del BPMN.`);
      continue;
    }
    waits[id] = parsed;
  }
  const arrivalPeriods = list(value.arrival_time_calendar, "arrival_time_calendar").map((entry, index) => period(entry, `arrival_time_calendar[${index}]`));
  const samePeriods = (a: SimCalendar["periods"], b: SimCalendar["periods"]) => {
    const normalized = (periods: SimCalendar["periods"]) => periods.map((item) => ({
      ...item,
      begin: item.begin.replace(/(?::00(?:\.0{1,3})?)$/, ""),
      end: item.end.replace(/(?::00(?:\.0{1,3})?)$/, ""),
    }));
    return JSON.stringify(normalized(a)) === JSON.stringify(normalized(b));
  };
  let arrivalCalendarId: string | undefined;
  if (!samePeriods(arrivalPeriods, template.standard_calendar?.periods ?? [])) {
    const match = customCalendars.find((calendar) => samePeriods(calendar.periods, arrivalPeriods));
    if (match) arrivalCalendarId = match.id;
    else {
      arrivalCalendarId = "imported-arrival-calendar";
      if (customCalendars.some((calendar) => calendar.id === arrivalCalendarId)) throw new Error("Identificativo calendario arrivi già utilizzato.");
      customCalendars.push({ id: arrivalCalendarId, name: "Arrivi importati", periods: arrivalPeriods });
    }
  }
  return {
    ...base, resources, tasks, gateways, waits, calendars: customCalendars,
    arrivalIntervalMinutes: arrival.meanMinutes,
    arrival: { distribution: arrival.distribution, stdMinutes: arrival.stdMinutes, minMinutes: arrival.minMinutes, maxMinutes: arrival.maxMinutes, calendarId: arrivalCalendarId },
  };
}
