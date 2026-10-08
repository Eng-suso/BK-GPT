import { z } from "zod";
import type { ProcessProvenance } from "@/contracts/workspace";
import { sourceRefsFromDocumentation, splitTraceability } from "../bpmn/provenance";

const stepSchema = z.object({ id: z.string(), label: z.string(), description: z.string().nullable().optional(), actor_ids: z.array(z.string()), inputs: z.array(z.string()), outputs: z.array(z.string()) });
const planSchema = z.object({
  title: z.string(),
  actors: z.array(z.object({ id: z.string(), label: z.string() })),
  steps: z.array(stepSchema),
  data_objects: z.array(z.object({ id: z.string(), label: z.string() })),
  controls: z.array(z.object({ id: z.string(), label: z.string(), subject_ids: z.array(z.string()) })),
  structured_business_rules: z.array(z.object({ id: z.string(), label: z.string(), applies_to_ids: z.array(z.string()), consequence: z.string() })),
  consultant_findings: z.array(z.object({ id: z.string(), finding: z.string(), severity: z.string(), recommendation: z.string().nullable().optional() })),
});
export const reviewActionSchema = z.object({
  id: z.string(), node_id: z.string(), node_name: z.string(), base_revision: z.string(),
  kind: z.enum(["candidate", "as_is_proposal", "clarification", "deferred"]), title: z.string(), detail: z.string(),
  created_at: z.string(), created_by: z.string(), proposal_xml: z.string().nullable().optional(),
});
export const reviewStateSchema = z.object({
  process_id: z.string(), base_revision: z.string(), xml: z.string().nullable(),
  plan: planSchema.nullable(), actions: z.array(reviewActionSchema),
});
export type ReviewState = z.infer<typeof reviewStateSchema>;
export type ReviewAction = z.infer<typeof reviewActionSchema>;
export type ReviewActionKind = ReviewAction["kind"];
export type CreateReviewAction = Pick<ReviewAction, "id" | "node_id" | "base_revision" | "kind" | "title" | "detail">;
export type ReviewNode = { id: string; name: string; type: string; owner: string; refs: string[]; notes: string };
export type ReviewGraph = { nodes: ReviewNode[]; edges: Array<{ source: string; target: string; kind: "sequence" | "data" }> };
const BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL";
const TASKS = new Set(["task", "userTask", "manualTask", "serviceTask", "businessRuleTask", "scriptTask", "sendTask", "receiveTask"]);

/** Exact BPMN ids and compiler traceability only; never join plan and canvas by similar names. */
export function readReviewGraph(xml: string | null): ReviewGraph {
  if (!xml) return { nodes: [], edges: [] };
  const document = new DOMParser().parseFromString(xml, "text/xml");
  if (document.querySelector("parsererror")) throw new Error("Invalid BPMN XML");
  const elements = Array.from(document.getElementsByTagNameNS(BPMN, "*"));
  const lanes = elements.filter(element => element.localName === "lane");
  const nodes = elements.filter(element => TASKS.has(element.localName)).map(element => {
    const id = element.getAttribute("id") ?? "";
    const doc = Array.from(element.children).find(child => child.localName === "documentation")?.textContent ?? "";
    return { id, name: element.getAttribute("name") || id, type: element.localName,
      owner: lanes.find(lane => Array.from(lane.getElementsByTagNameNS(BPMN, "flowNodeRef")).some(ref => ref.textContent === id))?.getAttribute("name") ?? "",
      refs: sourceRefsFromDocumentation(doc), notes: splitTraceability(doc).notes };
  });
  const edges: ReviewGraph["edges"] = [];
  for (const element of elements) {
    if (element.localName === "sequenceFlow") {
      edges.push({ source: element.getAttribute("sourceRef") ?? "", target: element.getAttribute("targetRef") ?? "", kind: "sequence" });
    }
    if (element.localName === "dataInputAssociation" || element.localName === "dataOutputAssociation") {
      const source = element.getElementsByTagNameNS(BPMN, "sourceRef")[0]?.textContent;
      const target = element.getElementsByTagNameNS(BPMN, "targetRef")[0]?.textContent;
      const task = element.parentElement?.getAttribute("id");
      if (task && element.localName === "dataInputAssociation" && source) edges.push({ source, target: task, kind: "data" });
      if (task && element.localName === "dataOutputAssociation" && target) edges.push({ source: task, target, kind: "data" });
    }
  }
  return { nodes, edges };
}

/** Reachability is a dependency scope, not a prediction of changed performance. */
export function dependencyScope(graph: ReviewGraph, id: string) {
  const walk = (reverse: boolean) => {
    const visited = new Set([id]);
    const queue = [id];
    for (let index = 0; index < queue.length; index++) {
      for (const edge of graph.edges) {
        if (edge.kind !== "sequence") continue;
        const from = reverse ? edge.target : edge.source;
        const to = reverse ? edge.source : edge.target;
        if (from === queue[index] && !visited.has(to)) { visited.add(to); queue.push(to); }
      }
    }
    visited.delete(id);
    return graph.nodes.filter(node => visited.has(node.id));
  };
  return { upstream: walk(true), downstream: walk(false), documents: graph.edges.filter(edge => edge.kind === "data" && (edge.source === id || edge.target === id)).map(edge => edge.source === id ? edge.target : edge.source) };
}

export function inspectReviewNode(node: ReviewNode, graph: ReviewGraph, state: ReviewState, provenance?: ProcessProvenance) {
  const stepIds = node.refs.filter(ref => ref.startsWith("steps:")).map(ref => ref.slice(6));
  const steps = state.plan?.steps.filter(step => stepIds.includes(step.id)) ?? [];
  const actorIds = new Set(steps.flatMap(step => step.actor_ids));
  const owner = state.plan?.actors.filter(actor => actorIds.has(actor.id)).map(actor => actor.label).join(", ") || node.owner;
  const label = (id: string) => state.plan?.data_objects.find(object => object.id === id)?.label ?? id;
  const inputs = [...new Set(steps.flatMap(step => step.inputs))].map(label);
  const outputs = [...new Set(steps.flatMap(step => step.outputs))].map(label);
  const evidence = provenance?.elements.filter(element => node.refs.includes(element.sourceRef)) ?? [];
  const gaps: Array<"owner" | "input" | "output" | "evidence"> = [];
  if (!owner) gaps.push("owner");
  if (!inputs.length) gaps.push("input");
  if (!outputs.length) gaps.push("output");
  if (provenance && (!evidence.length || evidence.some(item => item.markStatus === "unverified"))) gaps.push("evidence");
  return { owner, inputs, outputs, evidence, gaps, steps, scope: dependencyScope(graph, node.id),
    controls: state.plan?.controls.filter(control => control.subject_ids.some(id => stepIds.includes(id))) ?? [],
    rules: state.plan?.structured_business_rules.filter(rule => rule.applies_to_ids.some(id => stepIds.includes(id))) ?? [],
  };
}
