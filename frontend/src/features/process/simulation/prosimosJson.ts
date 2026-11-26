import { DEFAULT_SCENARIO, type DurationDraft, type ScenarioDraft } from "./simulationScenario";
import type { DistributionName, ScenarioTemplate, SimCalendar } from "./simulationTypes";

/**
 * Uno scenario Prosimos (JSON) come bozza del pannello, con cio' che non entra dichiarato.
 *
 * Gemello di `backend/simulation/prosimos_import.py`: i casi di
 * `tests/fixtures/simulation/prosimos_import_cases.json` valgono per entrambi.
 * Regole: le sezioni di base si traducono; i metadati SIMOD si ignorano; le
 * sezioni non rappresentate restano fuori con un avviso `notImported`; i campi
 * sconosciuti con `ignoredField`; le probabilita' che non sommano a 1 si
 * normalizzano con `normalizedProbabilities`; il join a un solo percorso si
 * ignora con `ignoredGateway`. Resta un errore solo cio' che non si puo' simulare.
 */

type JsonObject = Record<string, unknown>;
export type ProsimosIdMapping = {
  tasks?: Record<string, string>;
  gateways?: Record<string, string>;
  flows?: Record<string, string>;
  waits?: Record<string, string>;
};
export type ProsimosImportWarning = {
  kind: "ignoredField" | "ignoredGateway" | "notImported" | "normalizedProbabilities";
  target: string;
};
export type ProsimosImport = { draft: ScenarioDraft; warnings: ProsimosImportWarning[] };

export const flowMappingKey = (gatewayId: string, flowId: string): string => `${gatewayId}::${flowId}`;
const CORE_SECTIONS = new Set([
  "resource_profiles", "arrival_time_distribution", "arrival_time_calendar",
  "gateway_branching_probabilities", "task_resource_distribution", "resource_calendars", "event_distribution",
]);
/** Metadati degli scenari SIMOD: non cambiano cosa si simula. */
const METADATA_SECTIONS = new Set(["process_model", "model_type", "granule_size"]);
const DISTRIBUTIONS: Record<string, DistributionName> = {
  fix: "fixed", fixed: "fixed", expon: "expon", uniform: "uniform",
  norm: "norm", lognorm: "lognorm", gamma: "gamma",
};
const PARAMETER_COUNT: Record<DistributionName, number> = { fixed: 1, uniform: 2, expon: 3, norm: 4, lognorm: 4, gamma: 4 };
const DAY = /^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)$/;
const TIME = /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$/;
const ARRIVAL_CALENDAR_ID = "imported-arrival-calendar";
const PROBABILITY_TOLERANCE = 0.001;

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
function notEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" || Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}
/** `23:59:59.999000` (SIMOD) diventa `23:59:59.999`: la bozza tiene i millisecondi. */
function millis(time: string): string {
  const dot = time.indexOf(".");
  return dot < 0 ? time : `${time.slice(0, dot)}.${time.slice(dot + 1, dot + 4)}`;
}

/** Un solo percorso con probabilita' 1: nessuna scelta da simulare. */
export function isPassThroughGateway(row: unknown): boolean {
  if (!row || typeof row !== "object" || Array.isArray(row)) return false;
  const probabilities = (row as JsonObject).probabilities;
  if (!Array.isArray(probabilities) || probabilities.length !== 1) return false;
  const only = probabilities[0];
  if (!only || typeof only !== "object" || Array.isArray(only)) return false;
  const value = (only as JsonObject).value;
  const share = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : NaN;
  return Number.isFinite(share) && Math.abs(share - 1) <= PROBABILITY_TOLERANCE;
}

class Reader {
  readonly warnings: ProsimosImportWarning[] = [];

  warn(kind: ProsimosImportWarning["kind"], target: string): void {
    if (!this.warnings.some((item) => item.kind === kind && item.target === target)) this.warnings.push({ kind, target });
  }

  keys(value: JsonObject, allowed: readonly string[], path: string): void {
    for (const key of Object.keys(value)) if (!allowed.includes(key)) this.warn("ignoredField", `${path}.${key}`);
  }

  duration(value: unknown, path: string): DurationDraft {
    const distribution = object(value, path);
    this.keys(distribution, ["distribution_name", "distribution_params"], path);
    const rawName = string(distribution.distribution_name, `${path}.distribution_name`);
    const name = DISTRIBUTIONS[rawName];
    if (!name) throw new Error(`${path}: distribuzione ${rawName} non supportata dal motore.`);
    const params = list(distribution.distribution_params, `${path}.distribution_params`).map((entry, index) => {
      const row = object(entry, `${path}.distribution_params[${index}]`);
      this.keys(row, ["value"], `${path}.distribution_params[${index}]`);
      return number(row.value, `${path}.distribution_params[${index}].value`);
    });
    const count = PARAMETER_COUNT[name];
    if (params.length !== count) throw new Error(`${path}: ${name} richiede ${count} parametri, trovati ${params.length}.`);
    if (name === "uniform") return { distribution: name, meanMinutes: (params[0] + params[1]) / 120, minMinutes: params[0] / 60, maxMinutes: params[1] / 60 };
    if (name === "fixed") return { distribution: name, meanMinutes: params[0] / 60 };
    if (name === "expon") return { distribution: name, meanMinutes: params[0] / 60, minMinutes: params[1] / 60, maxMinutes: params[2] / 60 };
    const std = name === "norm" ? params[1] : Math.sqrt(params[1]);
    return { distribution: name, meanMinutes: params[0] / 60, stdMinutes: std / 60, minMinutes: params[2] / 60, maxMinutes: params[3] / 60 };
  }

  period(value: unknown, path: string): SimCalendar["periods"][number] {
    const row = object(value, path);
    this.keys(row, ["from", "to", "beginTime", "endTime"], path);
    const fromDay = string(row.from, `${path}.from`);
    const toDay = string(row.to, `${path}.to`);
    if (!DAY.test(fromDay) || !DAY.test(toDay)) throw new Error(`${path}: giorno non valido.`);
    const begin = string(row.beginTime, `${path}.beginTime`);
    const end = string(row.endTime, `${path}.endTime`);
    if (!TIME.test(begin) || !TIME.test(end)) throw new Error(`${path}: orario non valido.`);
    return {
      from_day: fromDay as SimCalendar["periods"][number]["from_day"],
      to_day: toDay as SimCalendar["periods"][number]["to_day"],
      begin: millis(begin), end: millis(end),
    };
  }
}

function samePeriods(a: SimCalendar["periods"], b: SimCalendar["periods"]): boolean {
  const normalized = (periods: SimCalendar["periods"]) => periods.map((item) => ({
    ...item,
    begin: item.begin.replace(/(?::00(?:\.0{1,3})?)$/, ""),
    end: item.end.replace(/(?::00(?:\.0{1,3})?)$/, ""),
  }));
  return JSON.stringify(normalized(a)) === JSON.stringify(normalized(b));
}

export function importProsimosJson(value: JsonObject, current: ScenarioDraft | null, template: ScenarioTemplate | null, mapping: ProsimosIdMapping = {}): ProsimosImport {
  if (!template) throw new Error("Il modello BPMN deve essere caricato prima di importare un JSON Prosimos.");
  const reader = new Reader();
  const source = object(value, "scenario");
  for (const [key, item] of Object.entries(source)) {
    if (CORE_SECTIONS.has(key) || METADATA_SECTIONS.has(key)) continue;
    if (notEmpty(item)) reader.warn("notImported", key);
  }
  const base: ScenarioDraft = structuredClone(current ?? DEFAULT_SCENARIO);

  const calendars = list(source.resource_calendars, "resource_calendars").map((entry, index) => {
    const path = `resource_calendars[${index}]`;
    const row = object(entry, path);
    reader.keys(row, ["id", "name", "time_periods"], path);
    return {
      id: string(row.id, `${path}.id`),
      name: string(row.name, `${path}.name`),
      periods: list(row.time_periods, `${path}.time_periods`).map((item, i) => reader.period(item, `${path}.time_periods[${i}]`)),
    };
  });
  const standardId = template.standard_calendar?.id;
  const customCalendars = calendars.filter((calendar) => calendar.id !== standardId);
  const customIds = new Set(customCalendars.map((calendar) => calendar.id));

  const profiles = list(source.resource_profiles, "resource_profiles");
  if (!profiles.length) throw new Error("resource_profiles: almeno un profilo risorsa richiesto.");
  const resources: ScenarioDraft["resources"] = [];
  profiles.forEach((entry, profileIndex) => {
    const path = `resource_profiles[${profileIndex}]`;
    const profile = object(entry, path);
    reader.keys(profile, ["id", "name", "resource_list"], path);
    string(profile.id, `${path}.id`);
    string(profile.name, `${path}.name`);
    list(profile.resource_list, `${path}.resource_list`).forEach((item, index) => {
      const resourcePath = `${path}.resource_list[${index}]`;
      const row = object(item, resourcePath);
      reader.keys(row, ["id", "name", "cost_per_hour", "amount", "calendar", "assignedTasks"], resourcePath);
      const calendarId = row.calendar == null ? undefined : string(row.calendar, `${resourcePath}.calendar`);
      if (calendarId && calendarId !== standardId && !customIds.has(calendarId)) throw new Error(`Calendario risorsa non trovato: ${calendarId}.`);
      resources.push({
        id: string(row.id, `${resourcePath}.id`),
        name: string(row.name, `${resourcePath}.name`),
        costPerHour: number(row.cost_per_hour, `${resourcePath}.cost_per_hour`),
        amount: number(row.amount, `${resourcePath}.amount`),
        parametersConfirmed: true,
        ...(calendarId && calendarId !== standardId ? { calendarId } : {}),
      });
    });
  });
  const resourceIds = new Set(resources.map((resource) => resource.id));
  if (resourceIds.size !== resources.length) throw new Error("Identificativi risorsa duplicati tra i profili: assegnazione ambigua.");

  const taskIds = template.tasks.map((task) => task.element_id);
  const knownTasks = new Set(taskIds);
  const tasks: ScenarioDraft["tasks"] = {};
  list(source.task_resource_distribution, "task_resource_distribution").forEach((item, index) => {
    const path = `task_resource_distribution[${index}]`;
    const row = object(item, path);
    reader.keys(row, ["task_id", "resources"], path);
    const sourceId = string(row.task_id, `${path}.task_id`);
    const id = mapping.tasks?.[sourceId] || sourceId;
    if (!knownTasks.has(id)) throw new Error(`Attività non presente nel BPMN: ${id}.`);
    if (tasks[id]) throw new Error(`Attività ${id} assegnata da più elementi del JSON.`);
    const assignments = list(row.resources, `${path}.resources`).map((entry, i) => {
      const assignmentPath = `${path}.resources[${i}]`;
      const assignment = object(entry, assignmentPath);
      reader.keys(assignment, ["resource_id", "distribution_name", "distribution_params"], assignmentPath);
      const resourceId = string(assignment.resource_id, `${assignmentPath}.resource_id`);
      if (!resourceIds.has(resourceId)) throw new Error(`Risorsa non trovata per ${id}: ${resourceId}.`);
      return { resourceId, ...reader.duration({ distribution_name: assignment.distribution_name, distribution_params: assignment.distribution_params }, assignmentPath) };
    });
    if (!assignments.length) throw new Error(`${id}: nessuna risorsa assegnata.`);
    const [primary, ...otherAssignments] = assignments;
    tasks[id] = { ...primary, assignmentSource: "manual", ...(otherAssignments.length ? { otherAssignments } : {}) };
  });
  const missingTasks = taskIds.filter((id) => !tasks[id]);
  if (missingTasks.length) throw new Error(`Attività senza durata nel JSON: ${missingTasks.join(", ")}.`);

  const gatewayFlows = new Map(template.gateways.map((gateway) => [gateway.element_id, gateway.branches.map((branch) => branch.flow_id)]));
  const gateways: ScenarioDraft["gateways"] = {};
  list(source.gateway_branching_probabilities, "gateway_branching_probabilities").forEach((item, index) => {
    const path = `gateway_branching_probabilities[${index}]`;
    const row = object(item, path);
    reader.keys(row, ["gateway_id", "probabilities"], path);
    const sourceId = string(row.gateway_id, `${path}.gateway_id`);
    const id = mapping.gateways?.[sourceId] || sourceId;
    const flows = gatewayFlows.get(id);
    if (!flows && isPassThroughGateway(row)) {
      reader.warn("ignoredGateway", sourceId);
      return;
    }
    if (!flows) throw new Error(`Decisione non presente nel BPMN: ${id}.`);
    if (gateways[id]) throw new Error(`Decisione ${id} assegnata da più elementi del JSON.`);
    let shares: Record<string, number> = {};
    list(row.probabilities, `${path}.probabilities`).forEach((branch, i) => {
      const branchPath = `${path}.probabilities[${i}]`;
      const probability = object(branch, branchPath);
      reader.keys(probability, ["path_id", "value"], branchPath);
      const sourceFlowId = string(probability.path_id, `${branchPath}.path_id`);
      const flowId = mapping.flows?.[flowMappingKey(sourceId, sourceFlowId)] || sourceFlowId;
      if (!flows.includes(flowId)) throw new Error(`Flusso non presente nel BPMN: ${flowId}.`);
      if (flowId in shares) throw new Error(`Flusso ${flowId} assegnato da più percorsi del JSON.`);
      shares[flowId] = number(probability.value, `${branchPath}.value`);
    });
    const missingFlows = flows.filter((flowId) => !(flowId in shares));
    if (missingFlows.length) throw new Error(`Flussi senza probabilità per ${id}: ${missingFlows.join(", ")}.`);
    if (Object.values(shares).some((share) => share < 0)) throw new Error(`Le probabilità di ${id} non possono essere negative.`);
    const total = Object.values(shares).reduce((sum, share) => sum + share, 0);
    if (total <= 0) throw new Error(`Le probabilità di ${id} sommano a zero.`);
    if (Math.abs(total - 1) > PROBABILITY_TOLERANCE) {
      reader.warn("normalizedProbabilities", id);
      shares = Object.fromEntries(Object.entries(shares).map(([flowId, share]) => [flowId, share / total]));
    }
    gateways[id] = Object.fromEntries(Object.entries(shares).map(([flowId, share]) => [flowId, share * 100]));
  });

  const arrival = reader.duration(source.arrival_time_distribution, "arrival_time_distribution");

  const templateWaits = new Map((template.waits ?? []).map((wait) => [wait.element_id, wait]));
  const waits: NonNullable<ScenarioDraft["waits"]> = {};
  list(source.event_distribution ?? [], "event_distribution").forEach((item, index) => {
    const path = `event_distribution[${index}]`;
    const row = object(item, path);
    reader.keys(row, ["event_id", "distribution_name", "distribution_params"], path);
    const sourceId = string(row.event_id, `${path}.event_id`);
    const id = mapping.waits?.[sourceId] || sourceId;
    const templateWait = templateWaits.get(id);
    if (!templateWait) throw new Error(`${path}: evento ${id} non presente tra le attese del BPMN corrente.`);
    if (id in waits) throw new Error(`${path}: evento ${id} duplicato.`);
    const parsed = reader.duration({ distribution_name: row.distribution_name, distribution_params: row.distribution_params }, path);
    // Prosimos rappresenta un'attesa di messaggio non impostata come durata fissa zero.
    if (parsed.distribution === "fixed" && parsed.meanMinutes === 0) {
      if (templateWait.kind === "timer") throw new Error(`${path}: il timer ${id} ha durata zero; non può sostituire la durata del BPMN.`);
      return;
    }
    waits[id] = parsed;
  });

  const arrivalPeriods = list(source.arrival_time_calendar, "arrival_time_calendar").map((entry, index) => reader.period(entry, `arrival_time_calendar[${index}]`));
  let arrivalCalendarId: string | undefined;
  if (!samePeriods(arrivalPeriods, template.standard_calendar?.periods ?? [])) {
    const match = customCalendars.find((calendar) => samePeriods(calendar.periods, arrivalPeriods));
    if (match) arrivalCalendarId = match.id;
    else {
      if (customIds.has(ARRIVAL_CALENDAR_ID)) throw new Error("Identificativo calendario arrivi già utilizzato.");
      arrivalCalendarId = ARRIVAL_CALENDAR_ID;
      customCalendars.push({ id: ARRIVAL_CALENDAR_ID, name: "Arrivi importati", periods: arrivalPeriods });
    }
  }
  const draft: ScenarioDraft = {
    ...base, resources, tasks, gateways, waits, calendars: customCalendars,
    arrivalIntervalMinutes: arrival.meanMinutes,
    arrival: {
      distribution: arrival.distribution,
      ...(arrival.stdMinutes !== undefined ? { stdMinutes: arrival.stdMinutes } : {}),
      ...(arrival.minMinutes !== undefined ? { minMinutes: arrival.minMinutes } : {}),
      ...(arrival.maxMinutes !== undefined ? { maxMinutes: arrival.maxMinutes } : {}),
      ...(arrivalCalendarId !== undefined ? { calendarId: arrivalCalendarId } : {}),
    },
  };
  return { draft, warnings: reader.warnings };
}
