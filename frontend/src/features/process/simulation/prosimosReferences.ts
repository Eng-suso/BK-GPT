import { flowMappingKey, type ProsimosIdMapping } from "./prosimosJson";
import type { ScenarioTemplate } from "./simulationTypes";

type Source = Record<string, unknown>;
type Option = { id: string; label: string };
export type ProsimosReferenceField = { kind: keyof ProsimosIdMapping; source: string; key: string; options: Option[] };

function records(value: unknown): Source[] {
  return Array.isArray(value) ? value.filter((item): item is Source => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function id(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Only missing BPMN references need explicit re-binding; exact IDs stay untouched. */
export function prosimosReferenceFields(source: Source, template: ScenarioTemplate, mapping: ProsimosIdMapping): ProsimosReferenceField[] {
  const fields: ProsimosReferenceField[] = [];
  const tasks = new Set(template.tasks.map((item) => item.element_id));
  const gateways = new Map(template.gateways.map((item) => [item.element_id, item]));
  const waits = new Set((template.waits ?? []).map((item) => item.element_id));
  const taskOptions = template.tasks.map((item) => ({ id: item.element_id, label: item.name || item.element_id }));
  const gatewayOptions = template.gateways.map((item) => ({ id: item.element_id, label: item.name || item.element_id }));
  const waitOptions = (template.waits ?? []).map((item) => ({ id: item.element_id, label: `${item.name || item.element_id} · ${item.kind}` }));
  for (const row of records(source.task_resource_distribution)) {
    const sourceId = id(row.task_id);
    if (sourceId && !tasks.has(sourceId)) fields.push({ kind: "tasks", source: sourceId, key: sourceId, options: taskOptions });
  }
  for (const row of records(source.gateway_branching_probabilities)) {
    const sourceId = id(row.gateway_id);
    if (!sourceId) continue;
    if (!gateways.has(sourceId)) fields.push({ kind: "gateways", source: sourceId, key: sourceId, options: gatewayOptions });
    const target = gateways.get(mapping.gateways?.[sourceId] || sourceId);
    if (!target) continue;
    const targetFlows = new Set(target.branches.map((branch) => branch.flow_id));
    for (const branch of records(row.probabilities)) {
      const flowId = id(branch.path_id);
      if (flowId && !targetFlows.has(flowId)) fields.push({
        kind: "flows", source: `${sourceId} / ${flowId}`, key: flowMappingKey(sourceId, flowId),
        options: target.branches.map((candidate) => ({ id: candidate.flow_id, label: candidate.flow_name || candidate.target_name || candidate.flow_id })),
      });
    }
  }
  for (const row of records(source.event_distribution)) {
    const sourceId = id(row.event_id);
    if (sourceId && !waits.has(sourceId)) fields.push({ kind: "waits", source: sourceId, key: sourceId, options: waitOptions });
  }
  return fields;
}
