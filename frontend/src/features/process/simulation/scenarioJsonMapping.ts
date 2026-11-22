import type { ScenarioDraft } from "./simulationScenario";

export type NumericJsonField = { path: string; value: number };
export type NumericMapping = {
  totalCases?: string;
  arrivalIntervalMinutes?: string;
  arrivalUnit?: "seconds" | "minutes" | "hours";
  defaultTaskMinutes?: string;
  defaultTaskUnit?: "seconds" | "minutes" | "hours";
  tasks?: Record<string, string | undefined>;
  taskUnit?: "seconds" | "minutes" | "hours";
  resources?: Record<string, { amount?: string; costPerHour?: string }>;
  gateways?: Record<string, Record<string, string | undefined>>;
  probabilityUnit?: "fraction" | "percent";
};

/** Candidate values only. The original JSON stays in the selected local file. */
export function numericJsonFields(value: unknown): NumericJsonField[] {
  const result: NumericJsonField[] = [];
  const visit = (item: unknown, path: string, depth: number) => {
    if (result.length >= 2000 || depth > 12) return;
    const numeric = typeof item === "number" ? item : typeof item === "string" && item.trim() && /^-?\d+(\.\d+)?$/.test(item.trim()) ? Number(item) : NaN;
    if (Number.isFinite(numeric)) {
      result.push({ path, value: numeric });
      return;
    }
    if (Array.isArray(item)) {
      item.forEach((child, index) => visit(child, `${path}[${index}]`, depth + 1));
      return;
    }
    if (item && typeof item === "object") {
      Object.entries(item).forEach(([key, child]) => visit(child, path ? `${path}.${key}` : key, depth + 1));
    }
  };
  visit(value, "", 0);
  return result;
}

export function applyNumericJsonMapping(base: ScenarioDraft, fields: NumericJsonField[], mapping: NumericMapping): ScenarioDraft {
  const values = new Map(fields.map((field) => [field.path, field.value]));
  const selected = (path: string | undefined): number | undefined => {
    if (!path) return undefined;
    if (!values.has(path)) throw new Error(`Percorso JSON non trovato: ${path}.`);
    return values.get(path);
  };
  const minutes = (value: number, unit: NumericMapping["arrivalUnit"]) => unit === "seconds" ? value / 60 : unit === "hours" ? value * 60 : value;
  const totalCases = selected(mapping.totalCases);
  const arrival = selected(mapping.arrivalIntervalMinutes);
  const defaultTask = selected(mapping.defaultTaskMinutes);
  if (totalCases !== undefined && !(Number.isInteger(totalCases) && totalCases > 0)) throw new Error("Il numero di casi deve essere un intero positivo.");
  if (arrival !== undefined && arrival <= 0) throw new Error("Il tempo fra arrivi deve essere positivo.");
  if (defaultTask !== undefined && defaultTask <= 0) throw new Error("La durata predefinita deve essere positiva.");
  const tasks = { ...base.tasks };
  for (const [id, path] of Object.entries(mapping.tasks ?? {})) {
    const value = selected(path);
    if (value === undefined || !tasks[id]) continue;
    if (value <= 0) throw new Error(`Durata non valida per ${id}.`);
    if (tasks[id].distribution === "uniform") throw new Error(`La durata di ${id} è uniforme: configura minimo e massimo nella sezione Attività.`);
    tasks[id] = { ...tasks[id], meanMinutes: minutes(value, mapping.taskUnit) };
  }
  const resources = base.resources.map((resource) => {
    const fields = mapping.resources?.[resource.id];
    if (!fields) return resource;
    const amount = selected(fields.amount);
    const costPerHour = selected(fields.costPerHour);
    if (amount !== undefined && !(Number.isInteger(amount) && amount >= 1 && amount <= 1000)) throw new Error(`Capacità non valida per ${resource.name}.`);
    if (costPerHour !== undefined && costPerHour < 0) throw new Error(`Costo orario non valido per ${resource.name}.`);
    return { ...resource, ...(amount !== undefined ? { amount } : {}), ...(costPerHour !== undefined ? { costPerHour } : {}),
      ...(amount !== undefined && costPerHour !== undefined ? { parametersConfirmed: true } : {}) };
  });
  const gateways = { ...base.gateways };
  for (const [id, branches] of Object.entries(mapping.gateways ?? {})) {
    if (!gateways[id]) continue;
    const next = { ...gateways[id] };
    for (const [flowId, path] of Object.entries(branches)) {
      const value = selected(path);
      if (value === undefined || !(flowId in next)) continue;
      const percent = mapping.probabilityUnit === "fraction" ? value * 100 : value;
      if (percent < 0 || percent > 100) throw new Error(`Probabilità non valida per ${flowId}.`);
      next[flowId] = percent;
    }
    if (Object.values(branches).some(Boolean) && Math.abs(Object.values(next).reduce((sum, value) => sum + value, 0) - 100) > 0.001) {
      throw new Error(`Le probabilità della decisione ${id} devono sommare a 100%.`);
    }
    gateways[id] = next;
  }
  return {
    ...base,
    ...(totalCases !== undefined ? { totalCases } : {}),
    ...(arrival !== undefined ? { arrivalIntervalMinutes: minutes(arrival, mapping.arrivalUnit) } : {}),
    ...(defaultTask !== undefined ? { defaultTaskMinutes: minutes(defaultTask, mapping.defaultTaskUnit) } : {}),
    tasks, resources, gateways,
  };
}
