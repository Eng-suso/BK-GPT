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

/**
 * Le porte del BPMN con un solo ramo in uscita: punti in cui i percorsi si ricongiungono.
 * Non hanno una scelta da impostare, quindi non sono fra le decisioni del template; il
 * server le riconosce da solo ("merge_gateway"), il consulente non deve associarle.
 */
export function mergeGatewayIds(xml: string | null | undefined): ReadonlySet<string> {
  if (!xml) return new Set();
  const document = new DOMParser().parseFromString(xml, "application/xml");
  const outgoing = new Map<string, number>();
  for (const flow of Array.from(document.getElementsByTagNameNS("*", "sequenceFlow"))) {
    const source = flow.getAttribute("sourceRef");
    if (source) outgoing.set(source, (outgoing.get(source) ?? 0) + 1);
  }
  const merges = new Set<string>();
  for (const element of Array.from(document.getElementsByTagNameNS("*", "*"))) {
    const elementId = element.getAttribute("id");
    if (elementId && element.localName.endsWith("Gateway") && (outgoing.get(elementId) ?? 0) <= 1) merges.add(elementId);
  }
  return merges;
}

/** Only missing BPMN references need explicit re-binding; exact IDs stay untouched. */
export function prosimosReferenceFields(
  source: Source,
  template: ScenarioTemplate,
  mapping: ProsimosIdMapping,
  merges: ReadonlySet<string> = new Set(),
): ProsimosReferenceField[] {
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
    if (!sourceId || merges.has(sourceId)) continue;
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
