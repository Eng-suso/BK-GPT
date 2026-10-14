import React from "react";

import type { ReplayEngine, ReplayToken } from "../replay/replayEngine";
import {
  svc,
  type BpmnCanvas,
  type BpmnElementRegistry,
  type BpmnPoint,
  type BpmnShape,
  type BpmnViewer,
} from "./bpmnViewer";
import { routeBetween, routeLength, spreadAlong, type TokenRoute } from "./tokenRoute";

const SVG_NS = "http://www.w3.org/2000/svg";
const TOKEN_R = 7;
/** A queue is only signalled: a few overlapping dots above the node (the badge
 *  carries the count). Work in progress is one dot inside the node. Only cases
 *  on the move are drawn one by one. */
const QUEUE_SIGNAL_DOTS = 3;
const QUEUE_SIGNAL_GAP = 10;
/** Marker on a sequence flow while at least one token travels along it. */
const LIVE_FLOW = "sim-flow-live";
/** Marker on a flow a token has just left: the trail fades out in CSS. */
const RECENT_FLOW = "sim-flow-recent";
/** How long a travelled flow keeps its trail, in wall-clock milliseconds. */
const TRAIL_MS = 1400;

/** Starts and stops gently: a hop reads as a movement, not a jump. */
const easeInOut = (p: number): number => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);
/** Minimum distance between two tokens travelling the same route, aura included. */
const TRAIN_GAP = TOKEN_R * 2 + 4;

type TokenLayerProps = {
  viewer: BpmnViewer | null;
  engine: ReplayEngine | null;
};

/**
 * Draws the replay tokens as SVG circles on a dedicated diagram-js canvas layer,
 * so they pan / zoom with the diagram for free. Driven imperatively by the
 * engine's ReplayClock — no React re-render per frame.
 */
export function TokenLayer({ viewer, engine }: TokenLayerProps): null {
  React.useEffect(() => {
    if (!viewer || !engine) return;

    const canvas = svc<BpmnCanvas>(viewer, "canvas");
    const registry = svc<BpmnElementRegistry>(viewer, "elementRegistry");
    if (!canvas || !registry) return;

    let layer: SVGElement;
    try {
      layer = canvas.getLayer("sim-tokens", 800);
    } catch {
      return;
    }
    layer.classList.add("sim-token-layer");

    const reduceMotion = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const dots = new Map<string, SVGCircleElement>();
    const paths = new Map<string, TokenRoute | null>();
    let liveFlows = new Set<string>();
    // flow id -> when its trail ends (performance.now() ms)
    const trails = new Map<string, number>();
    // A flow's label ("Sì", "No") lights up with its line.
    const withLabel = (flow: string): string[] => (registry.get(`${flow}_label`) ? [flow, `${flow}_label`] : [flow]);
    const mark = (flow: string, marker: string, on: boolean): void => {
      for (const id of withLabel(flow)) (on ? canvas.addMarker : canvas.removeMarker).call(canvas, id, marker);
    };
    const routeFor = (from: string | null, to: string | null): TokenRoute | null => {
      const key = `${from ?? "^"}>${to ?? "$"}`;
      if (!paths.has(key)) paths.set(key, routeBetween(registry, from, to));
      return paths.get(key) ?? null;
    };

    const ensureDot = (caseId: string): SVGCircleElement => {
      let dot = dots.get(caseId);
      if (!dot) {
        dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("r", String(TOKEN_R));
        dot.setAttribute("class", "sim-token");
        layer.appendChild(dot);
        dots.set(caseId, dot);
      }
      return dot;
    };

    const render = (): void => {
      const tokens = engine.tokensAt();
      const seen = new Set<string>();
      const live = new Set<string>();

      // group tokens per node so they stack / spread instead of overlapping
      const queuedByNode = new Map<string, ReplayToken[]>();
      const activeByNode = new Map<string, ReplayToken[]>();
      for (const token of tokens) {
        if (token.at.kind !== "node") continue;
        const map = token.at.queued ? queuedByNode : activeByNode;
        const list = map.get(token.at.el) ?? [];
        list.push(token);
        map.set(token.at.el, list);
      }

      const place = (caseId: string, pos: BpmnPoint, state: string): void => {
        const dot = ensureDot(caseId);
        dot.setAttribute("cx", pos.x.toFixed(1));
        dot.setAttribute("cy", pos.y.toFixed(1));
        dot.dataset.state = state;
        seen.add(caseId);
      };

      // tokens on the move, grouped per route so a batch released together
      // travels as a train of separate dots instead of one blob
      const trains = new Map<string, { route: TokenRoute; tokens: ReplayToken[]; progress: number[] }>();

      for (const token of tokens) {
        if (token.at.kind === "flow" && !reduceMotion) {
          const route = routeFor(token.at.from, token.at.to);
          if (route && route.points.length >= 2) {
            const key = route.flows.join(">");
            const train = trains.get(key) ?? { route, tokens: [], progress: [] };
            train.tokens.push(token);
            train.progress.push(easeInOut(token.at.progress));
            trains.set(key, train);
            continue;
          }
        }
        const pos = resolvePosition(
          token,
          registry,
          queuedByNode,
          activeByNode,
        );
        if (!pos) continue;
        place(token.caseId, pos, pos.queued ? "queued" : "active");
      }

      for (const { route, tokens: riders, progress } of trains.values()) {
        const total = routeLength(route.points);
        const slots = spreadAlong(progress.map((p) => p * total), total, TRAIN_GAP);
        riders.forEach((token, i) => {
          // Always on the line: a train longer than the route overlaps instead
          // of running beside it, where the dots would look like flying.
          const { d } = slots[i];
          place(token.caseId, pointAlong(route.points, total ? d / total : 0), "moving");
        });
        for (const flow of route.flows) live.add(flow);
      }

      // the aura: light up the flows tokens are travelling along right now,
      // and leave a short trail on the ones they have just left
      const now = performance.now();
      for (const flow of liveFlows) {
        if (live.has(flow)) continue;
        mark(flow, LIVE_FLOW, false);
        mark(flow, RECENT_FLOW, true);
        trails.set(flow, now + TRAIL_MS);
      }
      for (const flow of live) {
        if (liveFlows.has(flow)) continue;
        mark(flow, RECENT_FLOW, false);
        trails.delete(flow);
        mark(flow, LIVE_FLOW, true);
      }
      for (const [flow, until] of trails) {
        if (until > now) continue;
        mark(flow, RECENT_FLOW, false);
        trails.delete(flow);
      }
      liveFlows = live;

      for (const [caseId, dot] of dots) {
        if (!seen.has(caseId)) {
          dot.remove();
          dots.delete(caseId);
        }
      }

    };

    const unsubscribe = engine.subscribeTick(render);

    return () => {
      unsubscribe();
      for (const dot of dots.values()) dot.remove();
      dots.clear();
      for (const flow of liveFlows) mark(flow, LIVE_FLOW, false);
      for (const flow of trails.keys()) mark(flow, RECENT_FLOW, false);
    };
  }, [viewer, engine]);

  return null;
}

type ResolvedPos = BpmnPoint & { queued: boolean };

function resolvePosition(
  token: ReplayToken,
  registry: BpmnElementRegistry,
  queuedByNode: Map<string, ReplayToken[]>,
  activeByNode: Map<string, ReplayToken[]>,
): ResolvedPos | null {
  if (token.at.kind === "flow") {
    // no drawable route (or reduced motion): show it at its destination
    const to = token.at.to ? registry.get(token.at.to) : undefined;
    return to ? { ...shapeCenter(to), queued: false } : null;
  }

  const shape = registry.get(token.at.el);
  if (!shape) return null;
  const center = shapeCenter(shape);
  const bottom = (shape.y ?? center.y) + (shape.height ?? 0);

  if (!token.at.queued) {
    // in progress: one dot inside the node, along its lower edge, however
    // many cases are being worked
    const peers = activeByNode.get(token.at.el) ?? [token];
    if (peers.indexOf(token) > 0) return null;
    return { x: center.x, y: bottom - 12, queued: false };
  }

  // queued: just a signal, a few overlapping dots centred above the node
  const peers = queuedByNode.get(token.at.el) ?? [token];
  const index = peers.indexOf(token);
  if (index >= QUEUE_SIGNAL_DOTS) return null;
  const shown = Math.min(peers.length, QUEUE_SIGNAL_DOTS);
  return {
    x: center.x - ((shown - 1) / 2) * QUEUE_SIGNAL_GAP + index * QUEUE_SIGNAL_GAP,
    y: (shape.y ?? center.y) - 12,
    queued: true,
  };
}

function shapeCenter(shape: BpmnShape): BpmnPoint {
  return {
    x: (shape.x ?? 0) + (shape.width ?? 0) / 2,
    y: (shape.y ?? 0) + (shape.height ?? 0) / 2,
  };
}


function pointAlong(waypoints: BpmnPoint[], progress: number): BpmnPoint {
  const segLengths: number[] = [];
  let total = 0;
  for (let i = 1; i < waypoints.length; i += 1) {
    const len = Math.hypot(
      waypoints[i].x - waypoints[i - 1].x,
      waypoints[i].y - waypoints[i - 1].y,
    );
    segLengths.push(len);
    total += len;
  }
  let target = Math.min(1, Math.max(0, progress)) * total;
  for (let i = 0; i < segLengths.length; i += 1) {
    if (target <= segLengths[i] || i === segLengths.length - 1) {
      const f = segLengths[i] === 0 ? 0 : target / segLengths[i];
      return {
        x: waypoints[i].x + (waypoints[i + 1].x - waypoints[i].x) * f,
        y: waypoints[i].y + (waypoints[i + 1].y - waypoints[i].y) * f,
      };
    }
    target -= segLengths[i];
  }
  return waypoints[waypoints.length - 1];
}
