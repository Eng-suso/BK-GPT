import type { CanvasElement } from "./types";

type OutlineService = { registerProvider: (provider: DeliROutline) => void };

/** Presentation only: a selection follows the BPMN symbol, never its label box. */
export class DeliROutline {
  static $inject = ["outline"];
  constructor(outline: OutlineService) { outline.registerProvider(this); }
  getOutline(element: CanvasElement) {
    if (element.waypoints) return undefined;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", "djs-outline delir-shape-outline");
    return path;
  }
  updateOutline(element: CanvasElement, outline: SVGElement) {
    if (outline.tagName.toLowerCase() !== "path") return false;
    const w = element.width, h = element.height, offset = 2;
    let d: string;
    if (/Event$/.test(element.type)) {
      const r = Math.min(w, h) / 2 + offset;
      d = `M${w / 2 - r},${h / 2}a${r},${r} 0 1,0 ${r * 2},0a${r},${r} 0 1,0 ${-r * 2},0`;
    } else if (/Gateway$/.test(element.type)) {
      d = `M${w / 2},${-offset}L${w + offset},${h / 2}L${w / 2},${h + offset}L${-offset},${h / 2}Z`;
    } else {
      const r = /Task$|Activity$|SubProcess$/.test(element.type) ? 14 : 3;
      d = `M${r - offset},${-offset}H${w + offset - r}Q${w + offset},${-offset} ${w + offset},${r - offset}V${h + offset - r}Q${w + offset},${h + offset} ${w + offset - r},${h + offset}H${r - offset}Q${-offset},${h + offset} ${-offset},${h + offset - r}V${r - offset}Q${-offset},${-offset} ${r - offset},${-offset}Z`;
    }
    outline.setAttribute("d", d);
    const kind = /StartEvent$/.test(element.type) ? "start" : /EndEvent$/.test(element.type) ? "end" : /Gateway$/.test(element.type) ? "gateway" : "task";
    outline.style.setProperty("--delir-selection-accent", `var(--domain-process-${kind}-icon)`);
    outline.setAttribute("data-selection-kind", kind);
    return true;
  }
}
