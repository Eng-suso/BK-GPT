/** Minimal structural types over the parts of bpmn-js this feature touches. */

export type BpmnModeler = {
  importXML: (xml: string) => Promise<unknown>;
  saveXML: (options?: { format?: boolean }) => Promise<{ xml?: string }>;
  destroy: () => void;
  get: (name: string) => unknown;
};

export type BpmnConnection = {
  id: string;
  type?: string;
  businessObject?: {
    $type?: string;
  };
  source?: unknown;
  target?: unknown;
  waypoints?: unknown[];
};

export type BpmnCanvasViewbox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type BpmnCanvasService = {
  zoom: (scale?: number | "fit-viewport", center?: unknown) => number;
  resized?: () => void;
  viewbox?: (box?: BpmnCanvasViewbox) => BpmnCanvasViewbox & {
    outer?: { width: number; height: number };
  };
};

export type BpmnEventBus = {
  on: (events: string | string[], callback: (event?: unknown) => void) => void;
};

export type BpmnDiagramElement = {
  id?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  waypoints?: Array<{ x: number; y: number }>;
};

export type BpmnRegistryElement = BpmnConnection & {
  type?: string;
};

export type BpmnElementRegistry = {
  filter: (
    predicate: (element: BpmnRegistryElement) => boolean,
  ) => BpmnRegistryElement[];
  getAll?: () => BpmnDiagramElement[];
  get?: (id: string) => unknown;
};

export type BpmnModeling = {
  layoutConnection: (connection: BpmnConnection) => void;
  updateProperties: (
    element: unknown,
    properties: Record<string, unknown>,
  ) => void;
};

export type BpmnFactory = {
  create: (type: string, props: Record<string, unknown>) => unknown;
};

export type BpmnElementSelection = {
  id: string;
  type: string;
  businessObject?: {
    name?: string;
    documentation?: Array<{ text?: string }>;
  };
};

export type SelectedBpmnElement = {
  id: string;
  type: string;
  name: string;
  documentation: string;
};
