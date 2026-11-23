import { NS } from "../canvas-engine/types";

type Bounds = { x: number; y: number; width: number; height: number; type: string };

const elements = (root: ParentNode, namespace: string, name: string): Element[] =>
  Array.from((root as Document).getElementsByTagNameNS(namespace, name));
const value = (element: Element, key: string): number => Number(element.getAttribute(key));
const set = (element: Element, key: string, numberValue: number): void => {
  element.setAttribute(key, String(Math.round(numberValue * 1000) / 1000));
};
const median = (values: number[]): number => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
};

function dock(shape: Bounds, toward: { x: number; y: number }): { x: number; y: number } {
  const centerX = shape.x + shape.width / 2;
  const centerY = shape.y + shape.height / 2;
  const dx = toward.x - centerX;
  const dy = toward.y - centerY;
  if (dx === 0 && dy === 0) return { x: centerX, y: centerY };
  const halfWidth = shape.width / 2;
  const halfHeight = shape.height / 2;
  const factor = /Gateway$/.test(shape.type)
    ? 1 / (Math.abs(dx) / halfWidth + Math.abs(dy) / halfHeight)
    : /Event$/.test(shape.type)
      ? 1 / Math.sqrt((dx / halfWidth) ** 2 + (dy / halfHeight) ** 2)
      : Math.min(halfWidth / Math.abs(dx || Number.EPSILON), halfHeight / Math.abs(dy || Number.EPSILON));
  return { x: centerX + dx * factor, y: centerY + dy * factor };
}

/** Convert compact foreign DI to readable DeliR geometry without changing BPMN semantics. */
export function normalizeImportedBpmn(xml: string): string {
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.querySelector("parsererror")) return xml;
  const semantic = new Map(elements(document, NS.bpmn, "*").filter((element) => element.id).map((element) => [element.id, element]));
  const shapes = elements(document, NS.bpmndi, "BPMNShape");
  const taskShapes = shapes.flatMap((shape) => {
    const definition = semantic.get(shape.getAttribute("bpmnElement") ?? "");
    const bounds = elements(shape, NS.dc, "Bounds")[0];
    return definition && bounds && /(?:task|activity)$/i.test(definition.localName) && value(bounds, "width") > 0 && value(bounds, "height") > 0
      ? [bounds] : [];
  });
  if (!taskShapes.length) return xml;
  const typicalWidth = median(taskShapes.map((bounds) => value(bounds, "width")));
  const typicalHeight = median(taskShapes.map((bounds) => value(bounds, "height")));
  if (typicalWidth >= 150 && typicalHeight >= 78) return xml;
  const scaleX = Math.min(2.4, Math.max(1, 160 / typicalWidth));
  const scaleY = Math.min(2.4, Math.max(1, 88 / typicalHeight));
  const normalized = new Map<string, Bounds>();
  for (const shape of shapes) {
    const id = shape.getAttribute("bpmnElement") ?? "";
    const definition = semantic.get(id);
    const bounds = elements(shape, NS.dc, "Bounds")[0];
    if (!definition || !bounds) continue;
    const x = value(bounds, "x") * scaleX;
    const y = value(bounds, "y") * scaleY;
    const oldWidth = value(bounds, "width") * scaleX;
    const oldHeight = value(bounds, "height") * scaleY;
    let width = oldWidth;
    let height = oldHeight;
    if (/(?:task|activity)$/i.test(definition.localName)) {
      width = Math.max(160, oldWidth);
      height = Math.max(88, oldHeight);
    } else if (/gateway$/i.test(definition.localName)) {
      width = height = Math.max(50, Math.min(oldWidth, oldHeight));
    } else if (/event$/i.test(definition.localName)) {
      width = height = Math.max(40, Math.min(oldWidth, oldHeight));
    }
    const result = { x: x + (oldWidth - width) / 2, y: y + (oldHeight - height) / 2, width, height, type: definition.localName };
    for (const key of ["x", "y", "width", "height"] as const) set(bounds, key, result[key]);
    normalized.set(id, result);
    for (const label of elements(shape, NS.bpmndi, "BPMNLabel")) {
      const labelBounds = elements(label, NS.dc, "Bounds")[0];
      if (!labelBounds) continue;
      set(labelBounds, "x", value(labelBounds, "x") * scaleX);
      set(labelBounds, "y", value(labelBounds, "y") * scaleY);
      set(labelBounds, "width", value(labelBounds, "width") * scaleX);
      set(labelBounds, "height", value(labelBounds, "height") * scaleY);
    }
  }
  for (const edge of elements(document, NS.bpmndi, "BPMNEdge")) {
    const definition = semantic.get(edge.getAttribute("bpmnElement") ?? "");
    const points = elements(edge, NS.di, "waypoint");
    const original = points.map((point) => ({ x: value(point, "x") * scaleX, y: value(point, "y") * scaleY }));
    if (original.length >= 2 && definition) {
      const source = normalized.get(definition.getAttribute("sourceRef") ?? "");
      const target = normalized.get(definition.getAttribute("targetRef") ?? "");
      if (source && !/Participant|Lane/.test(source.type)) original[0] = dock(source, original[1]);
      if (target && !/Participant|Lane/.test(target.type)) original[original.length - 1] = dock(target, original[original.length - 2]);
    }
    points.forEach((point, index) => { set(point, "x", original[index].x); set(point, "y", original[index].y); });
    for (const label of elements(edge, NS.bpmndi, "BPMNLabel")) {
      const labelBounds = elements(label, NS.dc, "Bounds")[0];
      if (!labelBounds) continue;
      set(labelBounds, "x", value(labelBounds, "x") * scaleX);
      set(labelBounds, "y", value(labelBounds, "y") * scaleY);
      set(labelBounds, "width", value(labelBounds, "width") * scaleX);
      set(labelBounds, "height", value(labelBounds, "height") * scaleY);
    }
  }
  return new XMLSerializer().serializeToString(document);
}
