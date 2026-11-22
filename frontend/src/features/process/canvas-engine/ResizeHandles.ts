import ResizeHandles from "diagram-js/lib/features/resize/ResizeHandles";
import { getReferencePoint } from "diagram-js/lib/features/resize/Resize";
import { i18n } from "@/lib/i18n";
import type { CanvasElement } from "./types";

const SVG = "http://www.w3.org/2000/svg";
type Services = ConstructorParameters<typeof ResizeHandles>;

/** DeliR presentation; native resize gestures and commands remain unchanged. */
export class DeliRResizeHandles extends ResizeHandles {
  static $inject = ["eventBus", "canvas", "selection", "resize"];
  private readonly canvas: Services[1];

  constructor(bus: Services[0], canvas: Services[1], selection: Services[2], resize: Services[3]) {
    super(bus, canvas, selection, resize);
    this.canvas = canvas;
    let scale = canvas.zoom();
    bus.on("canvas.viewbox.changed", () => {
      const next = canvas.zoom();
      if (next === scale) return;
      scale = next;
      this.removeResizers();
      const selected = selection.get();
      if (selected.length === 1) this.addResizer(selected[0]);
    });
  }

  override createResizer(element: CanvasElement, direction: string) {
    const point = getReferencePoint(element, direction);
    const group = document.createElementNS(SVG, "g");
    group.setAttribute("class", `djs-resizer djs-resizer-${element.id} djs-resizer-${direction} delir-resizer`);
    group.setAttribute("data-resize-element", element.id);
    group.setAttribute("transform", `translate(${point.x},${point.y}) scale(${1 / this.canvas.zoom()})`);

    const title = document.createElementNS(SVG, "title");
    if(i18n.exists("process:canvas.resizeHint")){title.textContent = i18n.t("process:canvas.resizeHint");group.append(title);}

    // Geometry is in screen pixels: a zoomed container never grows giant handles.
    const corner = direction.length === 2;
    const visual = document.createElementNS(SVG, corner ? "circle" : "rect");
    visual.setAttribute("class", "djs-resizer-visual");
    visual.setAttribute("pointer-events", "none");
    if (corner) {
      visual.setAttribute("r", "3.5");
    } else {
      const horizontal = direction === "n" || direction === "s";
      visual.setAttribute("x", horizontal ? "-8" : "-1.5");
      visual.setAttribute("y", horizontal ? "-1.5" : "-8");
      visual.setAttribute("width", horizontal ? "16" : "3");
      visual.setAttribute("height", horizontal ? "3" : "16");
      visual.setAttribute("rx", "1.5");
    }
    group.append(visual);

    const hit = document.createElementNS(SVG, "rect");
    hit.setAttribute("class", "djs-resizer-hit");
    for (const [key, value] of Object.entries({ x: direction.includes("w") ? -24 : direction.includes("e") ? 0 : -12, y: direction.includes("n") ? -24 : direction.includes("s") ? 0 : -12, width: 24, height: 24 })) {
      hit.setAttribute(key, String(value));
    }
    group.append(hit);
    this.canvas.getLayer("resizers").append(group);
    this.makeDraggable(element, group, direction);
  }
}
