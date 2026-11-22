import type { CanvasElement, Point } from "./types";

/** A drop transfers the selected subgraph, never silently changes flow kinds. */
export function canMoveElements(shapes: CanvasElement[], target: CanvasElement | undefined, elements: CanvasElement[], delta?: Point): boolean {
  if (!target) return true; // Initial drag validation has no hover target yet.
  if (!/Process$|Collaboration$|Participant$|Lane$|SubProcess$/.test(target.type)) return false;
  const roots = new Set(shapes.filter(el => !el.labelTarget && !el.waypoints));
  const moving = (element: CanvasElement | undefined): boolean => {
    while (element) { if (roots.has(element)) return true; element = element.parent; }
    return false;
  };
  if (moving(target)) return false;
  const parent = (element: CanvasElement) => roots.has(element) ? target : element.parent;
  const owner = (element: CanvasElement | undefined, pattern: RegExp): CanvasElement | undefined => {
    while (element && !pattern.test(element.type)) element = parent(element);
    return element;
  };
  for (const shape of roots) {
    if (/Participant$|Lane$/.test(shape.type) && shape.parent !== target) return false;
    if (target.type === "bpmn:Collaboration" && /Task$|Activity$|Event$|Gateway$|SubProcess$/.test(shape.type) && shape.parent !== target) return false;
    if (delta && /Participant$|Lane$|SubProcess$/.test(target.type) && !/Participant$|Lane$/.test(shape.type)) {
      if (shape.x + delta.x < target.x + (/Participant$|Lane$/.test(target.type) ? 30 : 0) || shape.y + delta.y < target.y || shape.x + delta.x + shape.width > target.x + target.width || shape.y + delta.y + shape.height > target.y + target.height) return false;
    }
  }
  for (const edge of elements) {
    if (!edge.waypoints || !edge.source || !edge.target || !moving(edge.source) && !moving(edge.target)) continue;
    if (edge.type === "bpmn:SequenceFlow" && owner(parent(edge.source), /Process$|Participant$|SubProcess$|Collaboration$/) !== owner(parent(edge.target), /Process$|Participant$|SubProcess$|Collaboration$/)) return false;
    if (edge.type === "bpmn:MessageFlow") {
      const from = owner(edge.source, /Participant$/), to = owner(edge.target, /Participant$/);
      if (!from || !to || from === to) return false;
    }
  }
  return true;
}
