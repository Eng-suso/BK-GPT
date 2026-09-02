import type {
  BpmnCanvasService,
  BpmnCanvasViewbox,
  BpmnDiagramElement,
  BpmnElementRegistry,
  BpmnEventBus,
  BpmnModeler,
  BpmnModeling,
  BpmnRegistryElement,
} from "./types";

export function canvas(modeler: BpmnModeler): BpmnCanvasService {
  return modeler.get("canvas") as BpmnCanvasService;
}

export function fitCanvas(modeler: BpmnModeler): void {
  const canvasService = canvas(modeler);
  canvasService.resized?.();

  const elements =
    (modeler.get("elementRegistry") as BpmnElementRegistry).getAll?.() ?? [];
  const bounds = getDiagramBounds(elements);
  const outer = canvasService.viewbox?.().outer;

  if (!bounds || !outer?.width || !outer.height || !canvasService.viewbox) {
    canvasService.zoom("fit-viewport");
    return;
  }

  // Always frame the whole diagram, centred, with padding. The old
  // `minReadableScale` floor cropped large diagrams (pinned top-left, let the
  // rest overflow off-screen) — worse than a smaller-but-complete view the user
  // can zoom into.
  canvasService.viewbox(
    withViewportPadding(bounds, outer.width / outer.height),
  );
}

export function isConnection(element: BpmnRegistryElement): boolean {
  return Boolean(
    element.id &&
      element.source &&
      element.target &&
      Array.isArray(element.waypoints),
  );
}

export function isDockableSequenceConnection(
  element: BpmnRegistryElement,
): boolean {
  return (
    isConnection(element) &&
    element.businessObject?.$type === "bpmn:SequenceFlow"
  );
}

export function getDiagramBounds(
  elements: BpmnDiagramElement[],
): BpmnCanvasViewbox | null {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const element of elements) {
    if (element.id === "__implicitroot") continue;

    if (
      typeof element.x === "number" &&
      typeof element.y === "number" &&
      typeof element.width === "number" &&
      typeof element.height === "number"
    ) {
      minX = Math.min(minX, element.x);
      minY = Math.min(minY, element.y);
      maxX = Math.max(maxX, element.x + element.width);
      maxY = Math.max(maxY, element.y + element.height);
    }

    for (const point of element.waypoints ?? []) {
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

export function withViewportPadding(
  bounds: BpmnCanvasViewbox,
  viewportRatio: number,
): BpmnCanvasViewbox {
  const paddingX = 140;
  const paddingY = 120;
  let x = bounds.x - paddingX;
  let y = bounds.y - paddingY;
  let width = bounds.width + paddingX * 2;
  let height = Math.max(bounds.height + paddingY * 2, 420);
  const boundsRatio = width / height;

  if (boundsRatio > viewportRatio) {
    const centeredHeight = width / viewportRatio;
    y -= (centeredHeight - height) / 2;
    height = centeredHeight;
  } else {
    const centeredWidth = height * viewportRatio;
    x -= (centeredWidth - width) / 2;
    width = centeredWidth;
  }

  return { x, y, width, height };
}

export function keepSequenceConnectionsDocked(modeler: BpmnModeler): void {
  const eventBus = modeler.get("eventBus") as BpmnEventBus;
  const elementRegistry = modeler.get("elementRegistry") as BpmnElementRegistry;
  const modeling = modeler.get("modeling") as BpmnModeling;
  let scheduled = false;

  function scheduleRelayout() {
    if (scheduled) return;

    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      for (const connection of elementRegistry.filter(
        isDockableSequenceConnection,
      )) {
        try {
          modeling.layoutConnection(connection);
        } catch {
          // Transient invalid connections while the user drags the diagram —
          // the next relayout frame fixes them; nothing actionable to log.
        }
      }
    });
  }

  eventBus.on(
    [
      "commandStack.shape.move.postExecuted",
      "commandStack.elements.move.postExecuted",
      "commandStack.shape.resize.postExecuted",
    ],
    scheduleRelayout,
  );
}
