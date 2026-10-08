import type { BpmnModeler } from "./types";
export type ElementKind = "task" | "automation" | "gateway" | "start" | "end" | "other";
export type CanvasElement = { id: string; name: string; type: string; kind: ElementKind };
type RegistryShape = { id: string; type: string; labelTarget?: unknown; x?: number; height?: number; businessObject?: { name?: string }; di?: { $attrs?: Record<string, unknown>; get?: (key: string) => unknown } };
const kinds: ElementKind[] = ["task", "automation", "gateway", "start", "end", "other"];
export function elementKind(type: string): ElementKind {
  if (/Gateway$/.test(type)) return "gateway";
  if (type === "bpmn:StartEvent") return "start";
  if (type === "bpmn:EndEvent") return "end";
  if (/:(ServiceTask|ScriptTask|BusinessRuleTask)$/.test(type)) return "automation";
  if (/Task$/.test(type) || type === "bpmn:SubProcess") return "task";
  return "other";
}
/** Read the current registry after every import/edit. Markers affect presentation,
 * never the XML or command stack, and explicit colours in imported DI take priority. */
export function readCanvasElements(modeler: Pick<BpmnModeler, "get">): CanvasElement[] {
  const registry = modeler.get("elementRegistry") as { getAll: () => RegistryShape[]; getGraphics?: (id: string) => SVGElement | undefined };
  const canvas = modeler.get("canvas") as { addMarker: (id: string, marker: string) => void; removeMarker: (id: string, marker: string) => void };
  return registry.getAll().filter((el) => !el.labelTarget && el.type !== "label" && typeof el.x === "number").map((el) => {
    const kind = elementKind(el.type);
    kinds.forEach((value) => canvas.removeMarker(el.id, `delir-type-${value}`));
    const customColour = ["bioc:fill", "bioc:stroke", "color:background-color", "color:border-color"].some((key) => el.di?.get?.(key) || el.di?.$attrs?.[key]);
    if (!customColour) canvas.addMarker(el.id, `delir-type-${kind}`);
    if (el.type === "bpmn:Lane" || el.type === "bpmn:Participant") {
      const visual = registry.getGraphics?.(el.id)?.querySelector(".djs-visual");
      visual?.querySelector(".delir-role-band")?.remove();
      if (!customColour && visual && el.height) {
        const band = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        band.setAttribute("class", "delir-role-band");
        band.setAttribute("width", "30");
        band.setAttribute("height", String(el.height));
        band.setAttribute("aria-hidden", "true");
        // Beneath the BPMN label/separator; do not replace the structural outline.
        visual.insertBefore(band, visual.children[1] ?? null);
      }
    }
    return { id: el.id, name: el.businessObject?.name?.trim() || "", type: el.type.replace(/^bpmn:/, ""), kind };
  });
}

export type CreationTool = { id: string; title: string; className?: string; group?: string; separator?: boolean };
export type PaletteService = { getEntries: () => Record<string, Omit<CreationTool, "id">>; triggerEntry: (id: string, action: string, event: Event) => void };
export function readCreationTools(modeler: BpmnModeler): CreationTool[] {
  const palette = modeler.get("palette") as PaletteService;
  return Object.entries(palette.getEntries()).map(([id, entry]) => ({ ...entry, id }));
}
