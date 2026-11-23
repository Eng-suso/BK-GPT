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

/** A hovered task, edge or moving shape is not a semantic container. Keep the
 * current parent when a drop cannot legally transfer the selection. */
export function moveTarget(shapes: CanvasElement[], hover: CanvasElement | undefined, elements: CanvasElement[], delta?: Point): CanvasElement | undefined {
  const roots = shapes.filter(shape => !shape.labelTarget && !shape.waypoints);
  if (!roots.length && shapes.length && shapes.every(shape => shape.labelTarget)) return shapes[0].parent;
  const current = roots[0]?.parent;
  // Hover is the element under the pointer, which can be a connection, label,
  // or a sibling node. Resolve ownership from the dropped bounds as well so a
  // shape placed inside a lane joins that lane even when the pointer is over a
  // child or the canvas reports the pool underneath.
  if (delta && roots.length && roots.every(shape => !/Participant$|Lane$/.test(shape.type))) {
    const containing = elements.filter(element => /Participant$|Lane$|SubProcess$/.test(element.type) &&
      roots.every(shape => shape.x + delta.x >= element.x + (/Participant$|Lane$/.test(element.type) ? 30 : 0) &&
        shape.y + delta.y >= element.y && shape.x + delta.x + shape.width <= element.x + element.width &&
        shape.y + delta.y + shape.height <= element.y + element.height))
      .sort((a, b) => a.width * a.height - b.width * b.height);
    for (const container of containing)
      if (canMoveElements(shapes, container, elements, delta)) return container;
    if (containing.length) return undefined;
  }
  let candidate = hover;
  while (candidate && !/Process$|Collaboration$|Participant$|Lane$|SubProcess$/.test(candidate.type)) candidate = candidate.parent;
  if (candidate && canMoveElements(shapes, candidate, elements, delta)) return candidate;
  return current && canMoveElements(shapes, current, elements, delta) ? current : undefined;
}
