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

const SVG_NS = "http://www.w3.org/2000/svg";
const TOKEN_R = 6;
const QUEUE_GAP = 15;
const QUEUE_MAX_DOTS = 6;

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
    let overflow: SVGTextElement | null = null;

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

      let overflowCount = 0;
      let overflowAnchor: BpmnPoint | null = null;

      for (const token of tokens) {
        const pos = resolvePosition(
          token,
          registry,
          queuedByNode,
          activeByNode,
          reduceMotion,
        );
        if (!pos) continue;
        if (pos.hidden) {
          overflowCount += 1;
          overflowAnchor = pos;
          continue;
        }
        const dot = ensureDot(token.caseId);
        dot.setAttribute("cx", pos.x.toFixed(1));
        dot.setAttribute("cy", pos.y.toFixed(1));
        dot.dataset.state = pos.queued ? "queued" : "active";
        seen.add(token.caseId);
      }

      for (const [caseId, dot] of dots) {
        if (!seen.has(caseId)) {
          dot.remove();
          dots.delete(caseId);
        }
      }

      if (overflowCount > 0 && overflowAnchor) {
        if (!overflow) {
          overflow = document.createElementNS(SVG_NS, "text");
          overflow.setAttribute("class", "sim-token-overflow");
          layer.appendChild(overflow);
        }
        overflow.setAttribute("x", (overflowAnchor.x + 4).toFixed(1));
        overflow.setAttribute("y", (overflowAnchor.y - 2).toFixed(1));
        overflow.textContent = `+${overflowCount}`;
      } else if (overflow) {
        overflow.remove();
        overflow = null;
      }
    };

    const unsubscribe = engine.subscribeTick(render);

    return () => {
      unsubscribe();
      for (const dot of dots.values()) dot.remove();
      dots.clear();
      overflow?.remove();
    };
  }, [viewer, engine]);

  return null;
}

type ResolvedPos = BpmnPoint & { queued: boolean; hidden?: boolean };

function resolvePosition(
  token: ReplayToken,
  registry: BpmnElementRegistry,
  queuedByNode: Map<string, ReplayToken[]>,
  activeByNode: Map<string, ReplayToken[]>,
  reduceMotion: boolean,
): ResolvedPos | null {
  if (token.at.kind === "flow") {
    if (reduceMotion) {
      const shape = registry.get(token.at.to);
      return shape ? { ...shapeCenter(shape), queued: false } : null;
    }
    const conn = findConnection(registry, token.at.from, token.at.to);
    if (conn?.waypoints && conn.waypoints.length >= 2) {
      return { ...pointAlong(conn.waypoints, token.at.progress), queued: false };
    }
    const to = registry.get(token.at.to);
    return to ? { ...shapeCenter(to), queued: false } : null;
  }

  const shape = registry.get(token.at.el);
  if (!shape) return null;
  const center = shapeCenter(shape);
  const bottom = (shape.y ?? center.y) + (shape.height ?? 0);

  if (!token.at.queued) {
    // active: a row along the node's lower edge, clear of the centred label
    const peers = activeByNode.get(token.at.el) ?? [token];
    const shown = Math.min(peers.length, QUEUE_MAX_DOTS);
    const index = Math.min(peers.indexOf(token), QUEUE_MAX_DOTS - 1);
    return {
      x: center.x - ((shown - 1) / 2) * QUEUE_GAP + index * QUEUE_GAP,
      y: bottom - 12,
      queued: false,
    };
  }

  // queued: a row just above the node's top edge
  const peers = queuedByNode.get(token.at.el) ?? [token];
  const index = peers.indexOf(token);
  const top = (shape.y ?? center.y) - 13;
  if (index >= QUEUE_MAX_DOTS) {
    return {
      x: center.x + ((QUEUE_MAX_DOTS + 1) / 2) * QUEUE_GAP,
      y: top,
      queued: true,
      hidden: true,
    };
  }
  const shown = Math.min(peers.length, QUEUE_MAX_DOTS);
  return {
    x: center.x - ((shown - 1) / 2) * QUEUE_GAP + index * QUEUE_GAP,
    y: top,
    queued: true,
  };
}

function shapeCenter(shape: BpmnShape): BpmnPoint {
  return {
    x: (shape.x ?? 0) + (shape.width ?? 0) / 2,
    y: (shape.y ?? 0) + (shape.height ?? 0) / 2,
  };
}

function findConnection(
  registry: BpmnElementRegistry,
  from: string,
  to: string,
): BpmnShape | undefined {
  return registry
    .filter(
      (el) =>
        Array.isArray(el.waypoints) &&
        el.source?.id === from &&
        el.target?.id === to,
    )
    .at(0);
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
