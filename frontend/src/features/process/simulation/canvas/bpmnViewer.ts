/** Minimal structural types for the bpmn-js `NavigatedViewer` services the
 * simulation canvas + token layer touch. Kept here so both share one contract. */

export type BpmnViewer = {
  importXML: (xml: string) => Promise<{ warnings?: unknown[] }>;
  destroy: () => void;
  get: (name: string) => unknown;
  on: (event: string, cb: (e: unknown) => void) => void;
};

export type BpmnOverlays = {
  add: (
    elementId: string,
    opts: {
      position: Record<string, number>;
      html: string;
      scale?: boolean | { min?: number; max?: number };
    },
  ) => string;
  clear: () => void;
};

export type BpmnCanvas = {
  zoom: (mode?: "fit-viewport" | number, center?: unknown) => number;
  resized?: () => void;
  addMarker: (elementId: string, marker: string) => void;
  removeMarker: (elementId: string, marker: string) => void;
  scrollToElement?: (elementId: string) => void;
  getLayer: (name: string, index?: number) => SVGElement;
};

export type BpmnPoint = { x: number; y: number };

export type BpmnShape = {
  id: string;
  type?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  waypoints?: BpmnPoint[];
  source?: { id?: string };
  target?: { id?: string };
};

export type BpmnElementRegistry = {
  get: (id: string) => BpmnShape | undefined;
  filter: (fn: (el: BpmnShape) => boolean) => BpmnShape[];
};

export function svc<T>(viewer: BpmnViewer | null, name: string): T | null {
  try {
    return (viewer?.get(name) as T) ?? null;
  } catch {
    return null;
  }
}
