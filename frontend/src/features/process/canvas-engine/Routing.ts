import { connectRectangles, repairConnection, withoutRedundantPoints } from "diagram-js/lib/layout/ManhattanLayout";
import { avoidObstacles } from "./routeObstacles";
import type { Registry } from "./types";
import type { CanvasElement, Point } from "./types";

type DockingPoint = Point & { original?: Point };
type Hints = { source?:CanvasElement; target?:CanvasElement; connectionStart?: DockingPoint; connectionEnd?: DockingPoint; waypoints?: Point[] };
const mid = (shape: CanvasElement): Point => ({ x: shape.x + shape.width / 2, y: shape.y + shape.height / 2 });

/** One route for the live preview and the committed connector. */
export class OrthogonalLayout {
  static $inject=["elementRegistry"];
  constructor(private registry?:Registry) {}
  layoutConnection(connection: CanvasElement, hints: Hints = {}): Point[] {
    const source = hints.source ?? connection.source, target = hints.target ?? connection.target;
    if (!source || !target) return connection.waypoints ?? [];
    const old = (hints.waypoints ?? connection.waypoints) as DockingPoint[] | undefined;
    const start = hints.connectionStart?.original ?? hints.connectionStart ?? old?.[0]?.original ?? mid(source);
    const end = hints.connectionEnd?.original ?? hints.connectionEnd ?? old?.at(-1)?.original ?? mid(target);
    const vertical = Math.abs(mid(source).y - mid(target).y) > Math.abs(mid(source).x - mid(target).x);
    const preferredLayouts = ["straight", vertical ? "v:v" : "h:h"];
    const points = old?.length && (hints.connectionStart || hints.connectionEnd)
      ? repairConnection(source, target, start, end, old, { preferredLayouts, connectionStart: Boolean(hints.connectionStart), connectionEnd: Boolean(hints.connectionEnd) })
      : connectRectangles(source, target, start, end, { preferredLayouts });
    const route = !old?.length && this.registry ? avoidObstacles(points,source,target,this.registry.getAll(),connection.type) : points;
    return withoutRedundantPoints(route);
  }
}
