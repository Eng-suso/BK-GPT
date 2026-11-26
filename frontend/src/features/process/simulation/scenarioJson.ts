import { parseScenarioDraft, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";
import { importProsimosJson, type ProsimosIdMapping, type ProsimosImport } from "./prosimosJson";

const FORMAT = "delir-scenario-draft";
const VERSION = 1;
const DRAFT_KEYS = new Set([
  "scenarioName", "totalCases", "arrivalIntervalMinutes", "arrival", "sla", "caseFixedCost",
  "warmupCases", "horizonDays", "replications", "defaultTaskMinutes", "resources",
  "excludedResourceIds", "tasks", "gateways", "calendars", "caseAttributes",
  "gatewayRules", "casePriorities", "dismissedClaims", "waits",
]);

function stableJson(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) =>
    item && typeof item === "object" && !Array.isArray(item)
      ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)))
      : item,
  );
}

export function exportScenarioJson(draft: ScenarioDraft, bpmnModelId: string): string {
  return JSON.stringify({ format: FORMAT, version: VERSION, bpmnModelId, draft }, null, 2);
}

export function importScenarioJson(
  text: string,
  bpmnModelId: string,
  template: ScenarioTemplate | null,
  currentDraft: ScenarioDraft | null = null,
  idMapping: ProsimosIdMapping = {},
): ProsimosImport {
  const file: unknown = JSON.parse(text);
  if (!file || typeof file !== "object" || Array.isArray(file)) throw new Error("Il file deve contenere un oggetto JSON.");
  const data = file as Record<string, unknown>;
  if ("resource_profiles" in data && "task_resource_distribution" in data) return importProsimosJson(data, currentDraft, template, idMapping);
  if (data.format !== FORMAT || data.version !== VERSION) throw new Error("Struttura JSON non associata automaticamente. Mappa i campi dello scenario prima di applicarli.");
  if (data.bpmnModelId !== bpmnModelId) throw new Error("Il file appartiene a un altro modello BPMN.");
  if (!data.draft || typeof data.draft !== "object" || Array.isArray(data.draft)) throw new Error("Il file non contiene uno scenario valido.");
  const raw = data.draft as Record<string, unknown>;
  const unknown = Object.keys(raw).filter((key) => !DRAFT_KEYS.has(key));
  if (unknown.length) throw new Error(`Parametri non riconosciuti: ${unknown.join(", ")}. Il file non è stato applicato.`);
  for (const key of ["scenarioName", "totalCases", "arrivalIntervalMinutes", "defaultTaskMinutes", "resources", "tasks", "gateways"]) {
    if (!(key in raw)) throw new Error(`Parametro obbligatorio mancante: ${key}.`);
  }
  const parsed = parseScenarioDraft(raw);
  // parseScenarioDraft repairs old local drafts. An explicit import must never silently lose data.
  const changed = Object.keys(raw).filter((key) => stableJson(raw[key]) !== stableJson((parsed as unknown as Record<string, unknown>)[key]));
  if (changed.length) throw new Error(`Il file contiene parametri non importabili senza modifiche: ${changed.join(", ")}.`);
  if (template) {
    const taskIds = new Set(template.tasks.map((task) => task.element_id));
    const gatewayIds = new Set(template.gateways.map((gateway) => gateway.element_id));
    const waitIds = new Set((template.waits ?? []).map((wait) => wait.element_id));
    const mismatched = [
      ...Object.keys(parsed.tasks).filter((id) => !taskIds.has(id)),
      ...Object.keys(parsed.gateways).filter((id) => !gatewayIds.has(id)),
      ...Object.keys(parsed.waits ?? {}).filter((id) => !waitIds.has(id)),
    ];
    if (mismatched.length) throw new Error(`Elementi non presenti nel BPMN corrente: ${mismatched.join(", ")}.`);
  }
  return { draft: parsed, warnings: [] };
}
