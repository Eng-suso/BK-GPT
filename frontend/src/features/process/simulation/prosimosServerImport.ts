import { z } from "zod";

import { http } from "@/lib/http";

import { flowMappingKey, type ProsimosIdMapping } from "./prosimosJson";
import { simulationRunSchema, type SimulationRun } from "./simulationTypes";

// Il limite di ``CreateSimulationModelRunRequest.scenario_name`` sul server.
const SCENARIO_NAME_MAX = 200;

/** B1b: uno scenario Prosimos o SIMOD che l'editor non sa rappresentare, letto dal server. */
const noteSchema = z.object({
  kind: z.enum(["info", "approximated"]),
  topic: z.string(),
  message: z.string(),
  element_id: z.string().nullable().optional(),
});

export const prosimosImportSchema = z.object({
  bpmn_model_id: z.string(),
  // Il modello IR torna intero al server per il run: qui se ne leggono solo i conteggi.
  model: z.object({
    activities: z.array(z.unknown()),
    pools: z.array(z.object({ resources: z.array(z.unknown()) }).loose()),
    gateways: z.array(z.unknown()).default([]),
    waits: z.array(z.unknown()).default([]),
  }).loose(),
  notes: z.array(noteSchema),
  simod: z.record(z.string(), z.unknown()).default({}),
});

export type ProsimosImport = z.infer<typeof prosimosImportSchema>;
export type ProsimosImportNote = z.infer<typeof noteSchema>;

export type ImportSummary = { activities: number; resources: number; decisions: number; waits: number; fromSimod: boolean };

export function importSummary(result: ProsimosImport): ImportSummary {
  return {
    activities: result.model.activities.length,
    resources: result.model.pools.reduce((total, pool) => total + pool.resources.length, 0),
    decisions: result.model.gateways.length,
    waits: result.model.waits.length,
    fromSimod: Object.keys(result.simod).length > 0,
  };
}

export type NoteGroup = { topic: string; kind: ProsimosImportNote["kind"]; notes: ProsimosImportNote[] };

/** Le note per argomento, prima quelle da verificare: 16 attivita' istantanee sono una riga, non sedici. */
export function groupNotes(notes: ProsimosImportNote[]): NoteGroup[] {
  const groups = new Map<string, NoteGroup>();
  for (const note of notes) {
    const group = groups.get(note.topic) ?? { topic: note.topic, kind: note.kind, notes: [] };
    if (note.kind === "approximated") group.kind = "approximated";
    group.notes.push(note);
    groups.set(note.topic, group);
  }
  return [...groups.values()].sort((a, b) => Number(b.kind === "approximated") - Number(a.kind === "approximated"));
}

type Json = Record<string, unknown>;
const rows = (value: unknown): Json[] => (Array.isArray(value) ? value.filter((row): row is Json => !!row && typeof row === "object") : []);

/** Lo scenario con gli id che il consulente ha ricondotto al BPMN, per il server. Non modifica l'originale. */
export function remapProsimosIds(source: Json, mapping: ProsimosIdMapping): Json {
  const task = (id: unknown) => (typeof id === "string" && mapping.tasks?.[id]) || id;
  return {
    ...source,
    resource_profiles: rows(source.resource_profiles).map((profile) => ({
      ...profile,
      resource_list: rows(profile.resource_list).map((resource) => ({
        ...resource,
        ...(Array.isArray(resource.assignedTasks) ? { assignedTasks: resource.assignedTasks.map(task) } : {}),
      })),
    })),
    task_resource_distribution: rows(source.task_resource_distribution).map((row) => ({ ...row, task_id: task(row.task_id) })),
    gateway_branching_probabilities: rows(source.gateway_branching_probabilities).map((row) => {
      const gateway = String(row.gateway_id ?? "");
      return {
        ...row,
        gateway_id: mapping.gateways?.[gateway] || row.gateway_id,
        probabilities: rows(row.probabilities).map((path) => ({
          ...path,
          path_id: mapping.flows?.[flowMappingKey(gateway, String(path.path_id ?? ""))] || path.path_id,
        })),
      };
    }),
    ...(source.event_distribution !== undefined ? {
      event_distribution: rows(source.event_distribution).map((row) => ({
        ...row, event_id: (typeof row.event_id === "string" && mapping.waits?.[row.event_id]) || row.event_id,
      })),
    } : {}),
  };
}

export async function importProsimosOnServer(
  bpmnModelId: string,
  scenario: Record<string, unknown>,
  currentBpmnXml: string | null,
): Promise<ProsimosImport> {
  const raw = await http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}/prosimos-import`, {
    method: "POST",
    body: { scenario, current_bpmn_xml: currentBpmnXml },
  });
  return prosimosImportSchema.parse(raw);
}

export async function runImportedModel(
  bpmnModelId: string,
  input: { model: ProsimosImport["model"]; currentBpmnXml: string | null; totalCases: number; horizonDays?: number; scenarioName: string },
): Promise<SimulationRun> {
  const raw = await http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}/simulation-model-runs`, {
    method: "POST",
    body: {
      model: input.model,
      current_bpmn_xml: input.currentBpmnXml,
      total_cases: input.totalCases,
      ...(input.horizonDays !== undefined ? { horizon_days: input.horizonDays } : {}),
      scenario_name: input.scenarioName.slice(0, SCENARIO_NAME_MAX),
    },
  });
  return simulationRunSchema.parse(raw);
}
