import type { CanvasElement } from "./elements";

export type ElementRow = { element: CanvasElement; depth: number };

/** Keep BPMN ownership visible without changing the diagram or its XML. */
export function elementHierarchy(elements: CanvasElement[], query = ""): ElementRow[] {
  const byId = new Map(elements.map(element => [element.id, element]));
  const children = new Map<string, CanvasElement[]>();
  const roots: CanvasElement[] = [];
  for (const element of elements) {
    const parentId = element.parentId;
    if (!parentId || parentId === element.id || !byId.has(parentId)) roots.push(element);
    else children.set(parentId, [...(children.get(parentId) ?? []), element]);
  }

  const needle = query.trim().toLocaleLowerCase();
  const matching = new Set<string>();
  if (needle) for (const element of elements) {
    if (!`${element.name} ${element.type} ${element.id}`.toLocaleLowerCase().includes(needle)) continue;
    matching.add(element.id);
    let parentId = element.parentId;
    const seen = new Set([element.id]);
    while (parentId && byId.has(parentId) && !seen.has(parentId)) {
      matching.add(parentId);
      seen.add(parentId);
      parentId = byId.get(parentId)?.parentId;
    }
  }

  const rows: ElementRow[] = [];
  const visited = new Set<string>();
  const visit = (element: CanvasElement, depth: number, ancestorMatches: boolean) => {
    if (visited.has(element.id)) return;
    visited.add(element.id);
    const directMatch = !needle || `${element.name} ${element.type} ${element.id}`.toLocaleLowerCase().includes(needle);
    const show = !needle || ancestorMatches || matching.has(element.id);
    if (show) rows.push({ element, depth });
    for (const child of children.get(element.id) ?? []) visit(child, depth + 1, ancestorMatches || directMatch);
  };
  roots.forEach(element => visit(element, 0, false));
  // Imported diagrams can contain malformed parent cycles. Keep every element reachable.
  elements.forEach(element => visit(element, 0, false));
  return rows;
}
