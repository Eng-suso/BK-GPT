import type { Bus, CanvasElement, Point } from "./types";
import { OrthogonalLayout } from "./Routing";
import { DeliRRenderer } from "./Renderer";

const SVG = "http://www.w3.org/2000/svg";

type MoveContext = { shapes: CanvasElement[]; preview?: SVGElement; connections?: Array<{ element: CanvasElement; gfx: SVGElement; sourceMoves: boolean; targetMoves: boolean }> };
type MoveEvent = { context: MoveContext; dx: number; dy: number };
type Canvas = { getActiveLayer: () => SVGElement };

export function movedConnectionWaypoints(connection: CanvasElement, delta: Point, sourceMoves: boolean, targetMoves: boolean): Point[] {
  const old = connection.waypoints ?? [];
  if (old.length < 2 || !connection.source || !connection.target) return old;
  const shift = (point: Point): Point => ({ x: point.x + delta.x, y: point.y + delta.y });
  if (sourceMoves && targetMoves) return old.map(shift);
  const source = sourceMoves ? { ...connection.source, x: connection.source.x + delta.x, y: connection.source.y + delta.y } : connection.source;
  const target = targetMoves ? { ...connection.target, x: connection.target.x + delta.x, y: connection.target.y + delta.y } : connection.target;
  return new OrthogonalLayout().layoutConnection({ ...connection, source, target }, {
    connectionStart: sourceMoves ? shift(old[0]) : old[0],
    connectionEnd: targetMoves ? shift(old[old.length - 1]) : old[old.length - 1],
  }).map(({ x, y }) => ({ x, y }));
}

/** diagram-js omits links with only one moving endpoint from its drag preview.
 * Draw their live routes without changing the model or its saved DI. */
export class ConnectionMovePreview {
  static $inject = ["eventBus", "canvas", "delirRenderer"];
  constructor(bus: Bus, canvas: Canvas, renderer: DeliRRenderer) {
    bus.on("shape.move.start", 450, value => {
      const context = (value as { context: MoveContext }).context;
      const moving = new Set<CanvasElement>();
      const visit = (shape: CanvasElement) => {
        if (moving.has(shape)) return;
        moving.add(shape);
        for (const child of shape.children ?? []) visit(child);
      };
      context.shapes.forEach(visit);
      const connections = new Set<CanvasElement>();
      for (const shape of moving) for (const edge of [...(shape.incoming ?? []), ...(shape.outgoing ?? [])]) connections.add(edge);
      const external = [...connections].filter(edge => edge.source && edge.target && moving.has(edge.source) !== moving.has(edge.target));
      if (!external.length) return;
      const preview = document.createElementNS(SVG, "g");
      preview.setAttribute("class", "delir-move-connection-preview");
      preview.setAttribute("pointer-events", "none");
      canvas.getActiveLayer().append(preview);
      context.preview = preview;
      context.connections = external.map(element => {
        const gfx = document.createElementNS(SVG, "g");
        preview.append(gfx);
        return { element, gfx, sourceMoves: moving.has(element.source!), targetMoves: moving.has(element.target!) };
      });
    });
    bus.on("shape.move.move", 400, value => {
      const { context, dx, dy } = value as MoveEvent;
      for (const { element, gfx, sourceMoves, targetMoves } of context.connections ?? []) {
        gfx.replaceChildren();
        renderer.drawConnection(gfx, { ...element, waypoints: movedConnectionWaypoints(element, { x: dx, y: dy }, sourceMoves, targetMoves) });
      }
    });
    bus.on("shape.move.cleanup", 400, value => {
      const context = (value as { context: MoveContext }).context;
      context.preview?.remove();
      delete context.preview;
      delete context.connections;
    });
  }
}
