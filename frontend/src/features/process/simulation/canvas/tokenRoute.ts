import type { BpmnElementRegistry, BpmnPoint, BpmnShape } from "./bpmnViewer";

const isFlow = (el: BpmnShape) => Array.isArray(el.waypoints) && el.type === "bpmn:SequenceFlow";
const isActivity = (el: BpmnShape | undefined) =>
  Boolean(el?.type && /Task$|SubProcess$|CallActivity$/.test(el.type));

/**
 * The drawn path a token follows between two steps: the sequence flows from
 * `from` to `to`, through any gateways and intermediate events in between
 * (fewest hops). `from: null` starts at a start event, `to: null` ends at an
 * end event. Waypoints of each flow are joined into one polyline; `flows` are
 * the sequence flows it crosses, so the canvas can light them up.
 */
export type TokenRoute = { points: BpmnPoint[]; flows: string[] };

export function routeBetween(
  registry: BpmnElementRegistry,
  from: string | null,
  to: string | null,
): TokenRoute | null {
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
  return {
    points: hops.flatMap((flow, i) => (i === 0 ? flow.waypoints! : flow.waypoints!.slice(1))),
    flows: hops.map((flow) => flow.id),
  };
}

/** A token's place in a train: distance along the route and side lane
 *  (0 on the line, then 1, -1, 2, -2 … beside it). */
export type TrainSlot = { d: number; lane: number };

/**
 * Spreads tokens that travel the same route so each one stays visible: going
 * back from the leader, every token keeps at least `gap` px behind the one ahead.
 * A train that does not fit slides forward to the start of the route; one longer
 * than the route runs in parallel lanes beside the line, so dots never overlap.
 * Returns the slots in the order given.
 */
export function spreadAlong(distances: number[], total: number, gap: number): TrainSlot[] {
  const order = distances.map((d, i) => ({ d: Math.min(Math.max(d, 0), total), i })).sort((a, b) => b.d - a.d);
  const out = new Array<TrainSlot>(order.length);
  const perLane = Math.max(1, Math.floor(total / gap) + 1);
  const lanes = Math.max(1, Math.ceil(order.length / perLane));
  for (let lane = 0; lane < lanes; lane += 1) {
    // round-robin, so the leaders of each lane run side by side
    const riders = order.filter((_, k) => k % lanes === lane);
    const placed: number[] = [];
    riders.forEach((r, k) => placed.push(k === 0 ? r.d : Math.min(r.d, placed[k - 1] - gap)));
    const shift = Math.max(0, -(placed.at(-1) ?? 0));
    const side = lane === 0 ? 0 : lane % 2 ? (lane + 1) / 2 : -lane / 2;
    riders.forEach((r, k) => (out[r.i] = { d: Math.min(total, placed[k] + shift), lane: side }));
  }
  return out;
}

export function routeLength(points: BpmnPoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  return total;
}
