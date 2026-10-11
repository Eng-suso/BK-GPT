import type { BpmnElementRegistry, BpmnPoint, BpmnShape } from "./bpmnViewer";

const isFlow = (el: BpmnShape) => Array.isArray(el.waypoints) && el.type === "bpmn:SequenceFlow";
const isActivity = (el: BpmnShape | undefined) =>
  Boolean(el?.type && /Task$|SubProcess$|CallActivity$/.test(el.type));

/**
 * The drawn path a token follows between two steps: the sequence flows from
 * `from` to `to`, through any gateways and intermediate events in between
 * (fewest hops). `from: null` starts at a start event, `to: null` ends at an
 * end event. Waypoints of each flow are joined into one polyline.
 */
export function routeBetween(
  registry: BpmnElementRegistry,
  from: string | null,
  to: string | null,
): BpmnPoint[] | null {
  const flows = registry.filter(isFlow);
  const out = new Map<string, BpmnShape[]>();
  for (const flow of flows) {
    const id = flow.source?.id;
    if (id) out.set(id, [...(out.get(id) ?? []), flow]);
  }
  const starts = from
    ? [from]
    : registry.filter((el) => el.type === "bpmn:StartEvent").map((el) => el.id);
  const reached = (id: string) =>
    to ? id === to : registry.get(id)?.type === "bpmn:EndEvent";

  const via = new Map<string, BpmnShape | null>(starts.map((id) => [id, null]));
  const queue = [...starts];
  let last: BpmnShape | null = null; // the flow that reaches the goal
  while (queue.length && !last) {
    const id = queue.shift()!;
    for (const flow of out.get(id) ?? []) {
      const next = flow.target?.id;
      if (!next) continue;
      // checked before "visited": a rework loop goes back to the step it left
      if (reached(next)) {
        last = flow;
        break;
      }
      if (via.has(next)) continue;
      via.set(next, flow);
      // only pass through gateways and events, never through another step
      if (!isActivity(registry.get(next))) queue.push(next);
    }
  }
  if (!last) return null;

  const hops: BpmnShape[] = [];
  for (let flow: BpmnShape | null | undefined = last; flow; flow = via.get(flow.source!.id!)) hops.unshift(flow);
  return hops.flatMap((flow, i) => (i === 0 ? flow.waypoints! : flow.waypoints!.slice(1)));
}
