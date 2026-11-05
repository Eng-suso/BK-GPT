export type Point = {
    x: number;
    y: number;
};
export type BusinessObject = {
    id: string;
    $type: string;
    name?: string;
    documentation?: Array<{
        text?: string;
    }>;
    $attrs: Record<string, unknown>;
    get: (key: string) => unknown;
    eventDefinitions?: Array<{
        $type: string;
    }>;
    [key: string]: unknown;
};
export type CanvasElement = {
    id: string;
    type: string;
    businessObject: BusinessObject;
    x: number;
    y: number;
    width: number;
    height: number;
    parent?: CanvasElement;
    children?: CanvasElement[];
    source?: CanvasElement;
    target?: CanvasElement;
    waypoints?: Point[];
    host?: CanvasElement;
    labelTarget?: CanvasElement;
    di?: {
        get: (key: string) => string | null;
    };
    incoming?: CanvasElement[];
    outgoing?: CanvasElement[];
};
export type Bus = {
    on: (events: string | string[], priority: number | ((...args: unknown[]) => unknown), callback?: (...args: unknown[]) => unknown) => void;
    fire: (name: string, data?: Record<string, unknown>) => unknown;
};
export type Registry = {
    get: (id: string) => CanvasElement | undefined;
    getAll: () => CanvasElement[];
    getGraphics: (el: string | CanvasElement) => SVGElement;
};
export type Factory = {
    create: (kind: string, attrs: Record<string, unknown>) => CanvasElement;
    createShape: (attrs: Record<string, unknown>) => CanvasElement;
    createLabel: (attrs: Record<string, unknown>) => CanvasElement;
    createConnection: (attrs: Record<string, unknown>) => CanvasElement;
    createRoot: (attrs: Record<string, unknown>) => CanvasElement;
};
export const NS = { bpmn: "http://www.omg.org/spec/BPMN/20100524/MODEL", bpmndi: "http://www.omg.org/spec/BPMN/20100524/DI", dc: "http://www.omg.org/spec/DD/20100524/DC", di: "http://www.omg.org/spec/DD/20100524/DI", delir: "https://delir.app/schema/bpmn/1.0" };
export function businessObject(type: string, attrs: Record<string, unknown> = {}): BusinessObject {
    const object = { ...attrs, id: String(attrs.id ?? ""), $type: type, $attrs: { ...(attrs.$attrs as Record<string, unknown> ?? {}) } } as BusinessObject;
    object.get = key => key.includes(":") ? object.$attrs[key] : object[key];
    return object;
}
