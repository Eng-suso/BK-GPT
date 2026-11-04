import Diagram from "diagram-js";
import SelectionModule from "diagram-js/lib/features/selection";
import { LaneCommand } from "./Lanes";
import { DeleteSelectionCommand, deletionTargets } from "./DeleteSelection";
import { ConnectionOrder } from "./ConnectionOrder";
import { laneChildren, partitionResize, validPartitionResize, type Bounds } from "./Partitions";
import { getMinResizeBounds } from "diagram-js/lib/features/resize/ResizeUtil";
import { connectionRule, canStartConnection, flowScope } from "./connectionRules";
import { DeliROutline } from "./Outline";
import OutlineModule from "diagram-js/lib/features/outline";
import OverlaysModule from "diagram-js/lib/features/overlays";
import ModelingModule from "diagram-js/lib/features/modeling";
import MoveModule from "diagram-js/lib/features/move";
import CreateModule from "diagram-js/lib/features/create";
import ConnectionPreviewModule from "diagram-js/lib/features/connection-preview";
import CroppingConnectionDocking from "diagram-js/lib/layout/CroppingConnectionDocking";
import { OrthogonalLayout } from "./Routing";
import ConnectModule from "diagram-js/lib/features/connect";
import GlobalConnectModule from "diagram-js/lib/features/global-connect";
import LassoModule from "diagram-js/lib/features/lasso-tool";
import SpaceModule from "diagram-js/lib/features/space-tool";
import ResizeModule from "diagram-js/lib/features/resize";
import { DeliRResizeHandles } from "./ResizeHandles";
import BendpointsModule from "diagram-js/lib/features/bendpoints";
import HoverFixModule from "diagram-js/lib/features/hover-fix";
import KeyboardModule from "diagram-js/lib/features/keyboard";
import CopyPasteModule from "diagram-js/lib/features/copy-paste";
import { copiedBusinessObject, sourceFragment } from "./clipboard";
import EditorActionsModule from "diagram-js/lib/features/editor-actions";
import { DeliRRenderer } from "./Renderer";
import { BpmnDocument } from "./BpmnDocument";
import { businessObject, type Bus, type CanvasElement, type Factory, type Point, type Registry } from "./types";
import { enterpriseEntries } from "../bpmn/enterprisePalette";
import { i18n } from "@/lib/i18n";
import type { CreationTool } from "../bpmn/elements";
type CanvasService = {
    getRootElement: () => CanvasElement;
    setRootElement: (el: CanvasElement) => void;
    addShape: (el: CanvasElement, parent?: CanvasElement) => void;
    addConnection: (el: CanvasElement, parent?: CanvasElement) => void;
    getContainer: () => HTMLElement;
    focus: () => void;
    scroll: (delta: {
        dx: number;
        dy: number;
    }) => void;
    zoom: (value?: number, center?: Point) => number;
};
type Modeling = {
    createShape: (shape: CanvasElement, position: Point, parent: CanvasElement) => CanvasElement;
    appendShape: (source: CanvasElement, shape: CanvasElement, position: Point, parent: CanvasElement, hints?: Record<string, unknown>) => CanvasElement;
    removeElements: (els: CanvasElement[]) => void;
    updateProperties?: (el: CanvasElement, properties: Record<string, unknown>) => void;
    connect: (source: CanvasElement, target: CanvasElement, attrs?: Record<string, unknown>) => CanvasElement;
};
type Commands = {
    registerHandler: (name: string, handler: unknown) => void;
    execute: (name: string, context: unknown) => void;
    clear: () => void;
    canUndo: () => boolean;
    canRedo: () => boolean;
    undo: () => void;
    redo: () => void;
};
type Selection = {
    get: () => CanvasElement[];
    select: (els: CanvasElement[] | CanvasElement) => void;
};
type PropertiesContext = {
    element: CanvasElement;
    properties: Record<string, unknown>;
    old?: Record<string, unknown>;
    oldType?: string;
};
class UpdateProperties {
    static $inject = ["elementRegistry"];
    constructor(private registry: Registry) { }
    private changed(element: CanvasElement) { return [element, ...this.registry.getAll().filter(el => el.labelTarget === element)]; }
    execute(context: PropertiesContext) {
        const { element, properties } = context;
        context.old = {};
        context.oldType = element.type;
        for (const [key, value] of Object.entries(properties)) {
            context.old[key] = key.includes(":") ? element.businessObject.$attrs[key] : element.businessObject[key];
            if (key.includes(":"))
                element.businessObject.$attrs[key] = value;
            else
                element.businessObject[key] = value;
        }
        if (typeof properties.$type === "string")
            element.type = properties.$type;
        return this.changed(element);
    }
    revert(context: PropertiesContext) { const { element } = context; for (const [key, value] of Object.entries(context.old ?? {})) {
        if (key.includes(":"))
            element.businessObject.$attrs[key] = value;
        else
            element.businessObject[key] = value;
    } element.type = context.oldType!; return this.changed(element); }
}
const basicTargets: Record<string, string> = { "create.task": "Task", "create.user-task": "UserTask", "create.service-task": "ServiceTask", "create.manual-task": "ManualTask", "create.script-task": "ScriptTask", "create.business-rule-task": "BusinessRuleTask", "create.send-task": "SendTask", "create.receive-task": "ReceiveTask", "create.start-event": "StartEvent", "create.end-event": "EndEvent", "create.intermediate-event": "IntermediateCatchEvent", "create.exclusive-gateway": "ExclusiveGateway", "create.parallel-gateway": "ParallelGateway", "create.participant-expanded": "Participant", "create.data-object": "DataObjectReference", "create.data-store": "DataStoreReference", "create.group": "Group" };
const targets = new Map([...Object.entries(basicTargets).map(([id, type]) => [id, { type: "bpmn:" + type }]), ...enterpriseEntries.map(entry => [entry.id, entry.target])] as Array<[
    string,
    {
        type: string;
        eventDefinitionType?: string;
    }
]>);
function size(type: string) { return /Event$/.test(type) ? { width: 36, height: 36 } : /Gateway$/.test(type) ? { width: 50, height: 50 } : /Participant|Lane/.test(type) ? { width: 600, height: 220 } : /DataObject|DataStore/.test(type) ? { width: 50, height: 64 } : { width: 160, height: 88 }; }
/** DeliR owns BPMN import, graphics, rules and UI. diagram-js is an MIT-licensed
 * generic SVG/command toolkit; no bpmn-js renderer, provider or watermark code. */
export class DeliRCanvas {
    private readonly diagram: Diagram;
    private document: BpmnDocument | null = null;
    private readonly editable: boolean;
    private disposed = false;
    constructor(options: {
        container: HTMLElement;
        editable?: boolean;
        [key: string]: unknown;
    }) {
        this.editable = Boolean(options.editable);
        options.container.classList.add("delir-diagram");
        const editModules = this.editable ? [ModelingModule, MoveModule, CreateModule, ConnectModule, ConnectionPreviewModule, GlobalConnectModule, LassoModule, SpaceModule, ResizeModule, BendpointsModule, HoverFixModule, CopyPasteModule, KeyboardModule, EditorActionsModule] : [];
        this.diagram = new Diagram({ canvas: { container: options.container, deferUpdate: false }, modules: [SelectionModule, OutlineModule, OverlaysModule, ...editModules, { __init__: ["delirRenderer", "delirOutline","delirConnectionOrder"], delirConnectionOrder:["type",ConnectionOrder], delirOutline: ["type", DeliROutline], delirRenderer: ["type", DeliRRenderer], resizeHandles: ["type", DeliRResizeHandles], layouter: ["type", OrthogonalLayout], connectionDocking: ["type", CroppingConnectionDocking] }] });
        const factory = this.diagram.get<Factory>("elementFactory"), original = factory.create.bind(factory);
        factory.create = (kind, attrs = {}) => {
            const type = String(attrs.type ?? (kind === "connection" ? "bpmn:SequenceFlow" : "bpmn:Task")), id = String(attrs.id ?? attrs.delirId ?? type.replace("bpmn:", "") + "_" + crypto.randomUUID().replaceAll("-", "").slice(0, 12));
            const bo = attrs.businessObject as CanvasElement["businessObject"] | undefined;
            if (bo && kind !== "label")
                bo.id = id;
            const dimensions = kind === "shape" ? size(type) : {};
            const target = { ...dimensions, ...attrs, id, type, businessObject: bo ?? businessObject(type, { id, name: "", documentation: [], eventDefinitions: typeof attrs.eventDefinitionType === "string" ? [{ $type: attrs.eventDefinitionType }] : [] }) };
            return original(kind, target);
        };
        if (this.editable)
            this.configureEditing();
        else if (options.navigation !== false)
            this.configureNavigation();
    }
    get(name: string): unknown {
        if (name === "palette")
            return { getEntries: () => this.paletteEntries(), triggerEntry: (id: string, _action: string, event: Event) => this.activate(id, event) };
        if (name === "contextPad")
            return { getEntries: (selection: CanvasElement | CanvasElement[]) => this.contextEntries(selection), triggerEntry: (id: string, _action: string, event: Event) => this.contextAction(id, event) };
        if (name === "bpmnFactory")
            return { create: (type: string, attrs: Record<string, unknown>) => ({ $type: type, ...attrs }) };
        return this.diagram.get(name);
    }
    on(name: string, callback: (event: unknown) => void) { this.diagram.get<Bus>("eventBus").on(name, callback); }
    async importXML(xml: string) {
        const document = new BpmnDocument(xml);
        if (this.disposed)
            return { warnings: [] };
        this.diagram.clear();
        this.document = document;
        const factory = this.diagram.get<Factory>("elementFactory"), canvas = this.diagram.get<CanvasService>("canvas"), registry = this.diagram.get<Registry>("elementRegistry");
        const root = factory.createRoot({ id: document.rootId, type: document.rootType, businessObject: businessObject(document.rootType, { id: document.rootId }) });
        canvas.setRootElement(root);
        const shapes = document.records.filter(r => !r.waypoints), pending = [...shapes];
        while (pending.length) {
            let inserted = 0;
            for (let i = pending.length - 1; i >= 0; i--) {
                const record = pending[i];
                if (record.parentId && record.parentId !== root.id && !registry.get(record.parentId) && pending.some(r => r.id === record.parentId))
                    continue;
                const shape = factory.createShape({ id: record.id, type: record.type, businessObject: record.businessObject, di: record.di, x: record.x, y: record.y, width: record.width, height: record.height });
                canvas.addShape(shape, registry.get(record.parentId ?? "") ?? root);
                pending.splice(i, 1);
                inserted++;
            }
            if (!inserted)
                throw new Error("Gerarchia BPMN non valida.");
        }
        for (const record of document.records) {
            const shape = registry.get(record.id);
            if (shape && typeof record.businessObject.attachedToRef === "string")
                shape.host = registry.get(record.businessObject.attachedToRef);
        }
        for (const record of document.records.filter(r => r.waypoints)) {
            const source = registry.get(record.sourceId ?? ""), target = registry.get(record.targetId ?? "");
            if (!source || !target)
                throw new Error("Il collegamento " + record.id + " riferisce un elemento non rappresentato nel diagramma.");
            const connection = factory.createConnection({ id: record.id, type: record.type, businessObject: record.businessObject, di: record.di, waypoints: record.waypoints, source, target });
            connection.waypoints = this.diagram.get<{getCroppedWaypoints:(connection:CanvasElement)=>Point[]}>("connectionDocking").getCroppedWaypoints(connection);
            canvas.addConnection(connection, connection.type === "bpmn:MessageFlow" ? root : flowScope(source.parent) ?? root);
        }
        for (const record of document.records) {
            const owner = registry.get(record.id);
            if (!owner)
                continue;
            let label = record.label;
            if (!label && owner.businessObject.name && (/Event$|Gateway$/.test(owner.type) || owner.waypoints)) {
                const point = owner.waypoints?.[Math.floor(owner.waypoints.length / 2)];
                label = { x: point ? point.x - 45 : owner.x + owner.width / 2 - 45, y: point ? point.y - 26 : owner.y + owner.height + 6, width: 90, height: 32 };
            }
            if (label)
                canvas.addShape(factory.createLabel({ id: record.id + "_label", type: "label", businessObject: owner.businessObject, labelTarget: owner, ...label }), owner.waypoints ? owner.parent ?? root : owner);
        }
        if (this.editable)
            this.diagram.get<Commands>("commandStack").clear();
        document.setBaseline(registry.getAll());
        this.diagram.get<Bus>("eventBus").fire("import.done", { warnings: [] });
        return { warnings: [] };
    }
    async saveXML(_options?: {
        format?: boolean;
    }) { if (!this.document)
        throw new Error("Nessun documento BPMN caricato."); return { xml: this.document.serialize(this.diagram.get<Registry>("elementRegistry").getAll()) }; }
    destroy() { this.disposed = true; this.diagram.destroy(); }
    private configureEditing() {
        const bus = this.diagram.get<Bus>("eventBus"), commands = this.diagram.get<Commands>("commandStack"), modeling = this.diagram.get<Modeling>("modeling");
        commands.registerHandler("delir.properties", UpdateProperties);
        const docking=this.diagram.get<{getCroppedWaypoints:(connection:CanvasElement)=>Point[]}>("connectionDocking");
        bus.on(["commandStack.connection.create.executed","commandStack.connection.layout.executed","commandStack.connection.updateWaypoints.executed"],1500,event=>{
            const {connection}=(event as {context:{connection:CanvasElement}}).context;
            if(connection.source && connection.target && connection.waypoints?.length) connection.waypoints=docking.getCroppedWaypoints(connection);
        });
        commands.registerHandler("delir.lanes", LaneCommand);
        commands.registerHandler("delir.deleteSelection", DeleteSelectionCommand);
        // Generic diagram-js resizing knows nothing about BPMN partitions.
        // Keep this relationship in reversible modeling commands, never CSS.
        type PartitionContext={shape:CanvasElement;newBounds:Bounds;hints?:Record<string,unknown>;delirPartitionPlan?:Map<CanvasElement,Bounds>};
        const partitionShape=(shape:CanvasElement)=>shape.type === "bpmn:Lane" || laneChildren(shape).length>0;
        bus.on("commandStack.shape.resize.preExecute",2000,value=>{
            const context=(value as {context:PartitionContext}).context;
            if(partitionShape(context.shape)&&!context.hints?.delirLanes)context.delirPartitionPlan=partitionResize(context.shape,context.newBounds);
        });
        bus.on("commandStack.shape.resize.postExecuted",2000,value=>{
            const {delirPartitionPlan}=(value as {context:PartitionContext}).context;
            const resizeModeling=this.diagram.get<{resizeShape:(shape:CanvasElement,bounds:Bounds,min?:unknown,hints?:Record<string,unknown>)=>void}>("modeling");
            for(const [element,box] of delirPartitionPlan ?? [])if(element.x!==box.x||element.y!==box.y||element.width!==box.width||element.height!==box.height)resizeModeling.resizeShape(element,box,undefined,{delirLanes:true});
        });
        bus.on("resize.start",1500,value=>{
            const context=(value as {context:{shape:CanvasElement;direction:string;minBounds?:Bounds}}).context;
            if(!partitionShape(context.shape))return;
            const work:CanvasElement[]=[];
            const collect=(owner:CanvasElement)=>{for(const child of owner.children??[])if(child.type === "bpmn:Lane")collect(child);else if(!child.waypoints){work.push(child);for(const label of child.children??[])if(label.labelTarget)work.push(label);}};
            collect(context.shape);
            const content=work.length ? {x:Math.min(...work.map(child=>child.x))-8,y:Math.min(...work.map(child=>child.y))-8,width:Math.max(...work.map(child=>child.x+child.width))-Math.min(...work.map(child=>child.x))+16,height:Math.max(...work.map(child=>child.y+child.height))-Math.min(...work.map(child=>child.y))+16} : undefined;
            context.minBounds=getMinResizeBounds(context.direction,context.shape,{width:100,height:Math.max(1,laneChildren(context.shape).length)*60},content);
        });
        bus.on("shape.move.start",1400,value=>{
            const context=(value as {context:{shape:CanvasElement;shapes:CanvasElement[];validatedShapes:CanvasElement[]}}).context;
            if(context.shape.type!=="bpmn:Lane")return;
            let owner=context.shape;
            while(owner.parent?.type === "bpmn:Lane" || owner.parent?.type === "bpmn:Participant")owner=owner.parent;
            context.shapes=context.validatedShapes=owner.type === "bpmn:Lane" && owner.parent ? laneChildren(owner.parent) : [owner];
            context.shape=owner;
        });
        bus.on("commandStack.element.copy.canExecute", 2000, () => true);
        bus.on("commandStack.connection.start.canExecute", 2000, value => {
            const source = (value as { context: { source?: CanvasElement } }).context.source;
            return canStartConnection(source);
        });
        modeling.updateProperties = (element, properties) => commands.execute("delir.properties", { element: element.labelTarget ?? element, properties });
        bus.on("commandStack.delir.properties.postExecuted", 2000, event => {
            const {element} = (event as {context:PropertiesContext}).context;
            if (!element.businessObject.name || !(/Event$|Gateway$|DataObjectReference$|DataStoreReference$/.test(element.type) || element.waypoints)) return;
            if (this.diagram.get<Registry>("elementRegistry").getAll().some(label => label.labelTarget === element)) return;
            const point = element.waypoints?.[Math.floor(element.waypoints.length / 2)];
            this.diagram.get<{createLabel:(owner:CanvasElement,position:Point,attributes:Record<string,unknown>,parent?:CanvasElement)=>void}>("modeling").createLabel(element, {x:point?.x ?? element.x + element.width/2, y:point ? point.y-16 : element.y+element.height+22}, {type:"label",businessObject:element.businessObject,width:92,height:32}, element.waypoints ? element.parent : element);
        });
        bus.on("selection.changed", 2000, event => {
            const chosen = (event as {
                newSelection: CanvasElement[];
            }).newSelection;
            if (chosen.some(el => el.labelTarget)) {
                this.diagram.get<Selection>("selection").select([...new Set(chosen.map(el => el.labelTarget ?? el))]);
                return false;
            }
        });
        bus.on("commandStack.shape.attach.canExecute", 2000, event => { const { shape, target } = (event as {
            context: {
                shape?: CanvasElement;
                target?: CanvasElement;
            };
        }).context; return shape?.type === "bpmn:BoundaryEvent" && Boolean(target && /Task$|SubProcess$|Activity$/.test(target.type)); });
        bus.on("commandStack.shape.resize.canExecute", 2000, event => { const { shape, newBounds } = (event as {
            context: {
                shape: CanvasElement;
                newBounds?: {
                    width: number;
                    height: number;
                };
            };
        }).context; if (shape.labelTarget || !/Participant$|Lane$|SubProcess$|Group$|TextAnnotation$/.test(shape.type))
            return false;
            if((event as {context:{hints?:{delirLanes?:boolean}}}).context.hints?.delirLanes)return true;
            if(newBounds && partitionShape(shape))return validPartitionResize(partitionResize(shape,newBounds as Bounds));
            return !newBounds || newBounds.width >= 100 && newBounds.height >= 60; });
        bus.on("commandStack.elements.move.canExecute", 2000, event => { const { target, shapes } = (event as {
            context: {
                target?: CanvasElement;
                shapes?: CanvasElement[];
            };
        }).context; if (!target)
            return true; if (!/Process$|Collaboration$|Participant$|Lane$|SubProcess$/.test(target.type))
            return false;
            const scope = (element: CanvasElement | undefined) => { while (element && !/Process$|Collaboration$|Participant$|SubProcess$/.test(element.type)) element = element.parent; return element; };
            if (shapes?.some(shape => !shape.labelTarget && !/TextAnnotation$|Group$/.test(shape.type) && scope(shape.parent) !== scope(target))) return false;
            return !shapes?.some(shape => { let parent: CanvasElement | undefined = target; while (parent) {
            if (parent === shape)
                return true;
            parent = parent.parent;
        } return false; }); });
        bus.on(["commandStack.connection.delete.preExecute","commandStack.shape.delete.preExecute"],2000,value=>{
            const context=(value as {context:{connection?:CanvasElement;shape?:CanvasElement}}).context;
            const owner=context.connection??context.shape;
            const labels=this.diagram.get<Registry>("elementRegistry").getAll().filter(el=>el.labelTarget===owner);
            if(labels.length)modeling.removeElements(labels);
        });
        bus.on("commandStack.shape.move.preExecute",2000,value=>{
            const context=(value as {context:{shape:CanvasElement;newParent?:CanvasElement}}).context;
            if(context.shape.labelTarget)context.newParent=context.shape.parent;
        });
        bus.on("commandStack.connection.layout.postExecuted", 2000, event => { const { connection, oldWaypoints } = (event as {
            context: {
                connection: CanvasElement;
                oldWaypoints?: Point[];
            };
        }).context; if (!oldWaypoints?.length || !connection.waypoints?.length)
            return; const center = (points: Point[]) => ({ x: (Math.min(...points.map(p => p.x)) + Math.max(...points.map(p => p.x))) / 2, y: (Math.min(...points.map(p => p.y)) + Math.max(...points.map(p => p.y))) / 2 }); const before = center(oldWaypoints), after = center(connection.waypoints); for (const label of this.diagram.get<Registry>("elementRegistry").getAll().filter(el => el.labelTarget === connection))
            this.diagram.get<{
                moveShape: (shape: CanvasElement, delta: Point, parent?: CanvasElement, index?: number, hints?: Record<string, unknown>) => void;
            }>("modeling").moveShape(label, { x: after.x - before.x, y: after.y - before.y }, undefined, undefined, { layout: false }); });
        bus.on("commandStack.connection.create.canExecute", 2000, event => {
            const {source,target} = (event as {context:{source?:CanvasElement;target?:CanvasElement}}).context;
            return connectionRule(source,target);
        });
        bus.on("commandStack.connection.create.preExecute", 2000, event => {
            const context = (event as {context:{source:CanvasElement;connection:CanvasElement;parent:CanvasElement}}).context;
            context.parent = context.connection.type === "bpmn:MessageFlow" ? this.diagram.get<CanvasService>("canvas").getRootElement() : flowScope(context.source.parent) ?? context.parent;
        });
        bus.on(["commandStack.shape.create.canExecute", "commandStack.elements.create.canExecute"], 2000, event => { const { target } = (event as {
            context: {
                target?: CanvasElement;
            };
        }).context; const shape = (event as {context:{shape?:CanvasElement}}).context.shape;
            if(shape?.type === "bpmn:Lane") return target?.type === "bpmn:Participant" || target?.type === "bpmn:Lane" || target?.type === "bpmn:Process" && laneChildren(target).length>0;
            if(shape?.type === "bpmn:Participant") return target?.type === "bpmn:Process" || target?.type === "bpmn:Collaboration";
            return target && /Process$|Collaboration$|Participant$|Lane$|SubProcess$/.test(target.type) ? true : false; });
        bus.on("commandStack.shape.create.preExecute",2000,event=>{
            const context=(event as {context:{shape:CanvasElement;parent:CanvasElement}}).context;
            // Dropping on a lane inserts a sibling in its owning partition set.
            if(context.shape.type === "bpmn:Lane" && context.parent?.type === "bpmn:Lane")context.parent=context.parent.parent!;
        });
        bus.on("commandStack.shape.create.postExecuted",2000,event=>{
            const {shape,parent,hints}=(event as {context:{shape:CanvasElement;parent:CanvasElement;hints?:Record<string,unknown>}}).context;
            if(shape.type === "bpmn:Lane" && (parent?.type === "bpmn:Participant" || parent?.type === "bpmn:Process") && !hints?.delirLanes) commands.execute("delir.lanes",{element:parent,action:"adopt",lane:shape});
        });
        bus.on("copyPaste.copyElement", 1500, event => { const { descriptor, element } = (event as {
            descriptor: Record<string, unknown>;
            element: CanvasElement;
        }); descriptor.type = element.type; descriptor.delirData = JSON.parse(JSON.stringify(element.businessObject)); descriptor.delirXml = sourceFragment(this.document, element.businessObject); descriptor.delirVisibleIds = this.document?.records.map(record => record.id) ?? []; });
        bus.on("copyPaste.pasteElement", 1500, event => {
            const { descriptor, cache } = (event as {
                descriptor: Record<string, unknown>;
                cache: Record<string, CanvasElement>;
            });
            const type = String(descriptor.type), id = type.replace("bpmn:", "") + "_" + crypto.randomUUID().replaceAll("-", "").slice(0, 12);
            descriptor.delirId = id;
            descriptor.businessObject = descriptor.labelTarget ? cache[String(descriptor.labelTarget)]?.businessObject : copiedBusinessObject(type, descriptor.delirData as Record<string, unknown>, id, descriptor.delirXml as string | undefined, new Set(descriptor.delirVisibleIds as string[]));
        });
        bus.on("commandStack.connection.reconnect.canExecute",2000,event=>{
            const {connection,source,target,newSource,newTarget}=(event as {context:{connection:CanvasElement;source?:CanvasElement;target?:CanvasElement;newSource?:CanvasElement;newTarget?:CanvasElement}}).context;
            if(/Data(Input|Output)Association$/.test(connection.type))return false;
            const rule=connectionRule(source ?? newSource ?? connection.source,target ?? newTarget ?? connection.target);
            return Boolean(rule && rule.type === connection.type);
        });
        const actions = this.diagram.get<{
            register: (id: string, callback: () => void) => void;
            unregister: (id: string) => void;
        }>("editorActions");
        actions.unregister("removeSelection");
        actions.register("removeSelection",()=>this.deleteSelection());
        actions.register("selectAll", () => this.diagram.get<Selection>("selection").select(this.diagram.get<Registry>("elementRegistry").getAll().filter(el => el.id !== this.document?.rootId && !el.labelTarget)));
        // KeyboardBindings registers defaults before the public action above.
        this.diagram.get<CanvasService>("canvas").getContainer().querySelector("svg")?.addEventListener("keydown", event => { const key = (event as KeyboardEvent); if(key.key === "F2" && !key.defaultPrevented) { const selected=this.diagram.get<Selection>("selection").get(); if(selected.length === 1) { key.preventDefault(); bus.fire("element.dblclick",{element:selected[0]}); } } else if ((key.ctrlKey || key.metaKey) && key.key.toLowerCase() === "a") {
            key.preventDefault();
            this.diagram.get<Selection>("selection").select(this.diagram.get<Registry>("elementRegistry").getAll().filter(el => el.id !== this.document?.rootId && !el.labelTarget));
        } });
    }
    private configureNavigation() {
        const canvas = this.diagram.get<CanvasService>("canvas"), host = canvas.getContainer(), svg = host.querySelector("svg")!;
        let start: Point | null = null;
        const down = (event: PointerEvent) => { if (event.button !== 0 && event.button !== 1)
            return; start = { x: event.clientX, y: event.clientY }; svg.setPointerCapture(event.pointerId); };
        const move = (event: PointerEvent) => { if (!start)
            return; canvas.scroll({ dx: event.clientX - start.x, dy: event.clientY - start.y }); start = { x: event.clientX, y: event.clientY }; };
        const up = () => { start = null; };
        const wheel = (event: WheelEvent) => { event.preventDefault(); const box = host.getBoundingClientRect(); if (event.ctrlKey || event.metaKey)
            canvas.zoom(Math.max(.2, Math.min(4, canvas.zoom() * Math.exp(-event.deltaY * .0015))), { x: event.clientX - box.left, y: event.clientY - box.top });
        else
            canvas.scroll({ dx: -event.deltaX, dy: -event.deltaY }); };
        svg.addEventListener("pointerdown", down);
        svg.addEventListener("pointermove", move);
        svg.addEventListener("pointerup", up);
        svg.addEventListener("pointercancel", up);
        host.addEventListener("wheel", wheel, { passive: false });
        this.on("diagram.destroy", () => { svg.removeEventListener("pointerdown", down); svg.removeEventListener("pointermove", move); svg.removeEventListener("pointerup", up); svg.removeEventListener("pointercancel", up); host.removeEventListener("wheel", wheel); });
    }
    private paletteEntries(): Record<string, CreationTool> {
        return Object.fromEntries([...targets.keys(), "hand-tool", "global-connect-tool", "lasso-tool", "space-tool"].map(id => [id, { id, title: i18n.t("process:canvas.tools." + id), group: id.endsWith("-tool") ? "tools" : /event/.test(id) ? "event" : /gateway/.test(id) ? "gateway" : /participant|lane/.test(id) ? "collaboration" : /data-|annotation|group/.test(id) ? "artifact" : "activity" }]));
    }
    private activate(id: string, event: Event) {
        if (!this.editable)
            return;
        if (id === "global-connect-tool") {
            this.diagram.get<{
                start: (event: Event) => void;
            }>("globalConnect").start(event);
            return;
        }
        if (id === "lasso-tool" || id === "space-tool") {
            this.diagram.get<{
                toggle: () => void;
            }>(id === "lasso-tool" ? "lassoTool" : "spaceTool").toggle();
            return;
        }
        const target = targets.get(id);
        if (!target)
            return;
        const shape = this.diagram.get<Factory>("elementFactory").createShape({ ...target });
        this.diagram.get<{
            start: (event: Event, shape: CanvasElement) => void;
        }>("create").start(event, shape);
    }
    private contextEntries(selection: CanvasElement | CanvasElement[]): Record<string, CreationTool> {
        if (!this.editable)
            return {};
        const selected = Array.isArray(selection) ? selection : [selection];
        if (!selected.length)
            return {};
        const entries: Record<string, CreationTool> = { delete: { id: "delete", title: i18n.t("process:canvas.context.delete") } };
        if (selected.length > 1) {
            entries.delete.title=i18n.t("process:canvas.interactions.deleteSelection");
            return entries;
        }
        const el = selected[0].labelTarget ?? selected[0];
        if (el.waypoints)
            return entries;
        if (canStartConnection(el)) entries.connect = { id: "connect", title: i18n.t("process:canvas.interactions.connect") };
        if (!/EndEvent|Participant|Lane|Group|Data|TextAnnotation/.test(el.type)) {
            for (const id of ["create.task", "create.exclusive-gateway", "create.end-event", "create.intermediate-event", "create.annotation"]) {
                const action = id.replace("create.", "append.");
                entries[action] = { id: action, title: i18n.t("process:canvas.context." + ({ "create.task": "task", "create.exclusive-gateway": "gateway", "create.end-event": "end", "create.intermediate-event": "intermediate", "create.annotation": "annotation" }[id])) };
            }
        }
        if (/Participant$|Lane$/.test(el.type)) {
            for(const action of ["add-above","add-below",...(!el.children?.some(child=>child.type === "bpmn:Lane") ? ["split-2","split-3"] : [])])
                entries["lane."+action] = {id:"lane."+action,title:i18n.t("process:canvas.lanes."+action)};
            if(el.type === "bpmn:Lane") entries.delete.title = i18n.t("process:canvas.lanes.remove");
        }
        const family = /Task$|Activity$|SubProcess$/.test(el.type) ? /Task$|Activity$|SubProcess$/ : /Gateway$/.test(el.type) ? /Gateway$/ : /StartEvent$/.test(el.type) ? /StartEvent$/ : /EndEvent$/.test(el.type) ? /EndEvent$/ : /BoundaryEvent$/.test(el.type) ? /BoundaryEvent$/ : /Intermediate.*Event$/.test(el.type) ? /Intermediate.*Event$/ : null;
        if (family)
            for (const [id, target] of targets)
                if (family.test(target.type) && (!el.children?.some(child => !child.labelTarget) || target.type === el.type)) {
                    const action = "replace." + id;
                    entries[action] = { id: action, title: i18n.t(id==="create.task" ? "process:canvas.legend.task" : "process:canvas.tools."+id),checked:target.type===el.type && (target.eventDefinitionType??"")===(el.businessObject.eventDefinitions?.[0]?.$type??"") };
                }
        return entries;
    }
    private contextAction(id: string, event: Event) {
        if (!this.editable)
            return;
        if(id === "select-all") { this.diagram.get<{trigger:(id:string)=>void}>("editorActions").trigger("selectAll");return; }
        if(id === "delete") {this.deleteSelection();return;}
        const selection = this.diagram.get<Selection>("selection"), selected = selection.get(), el = selected[0]?.labelTarget ?? selected[0];
        if (!el)
            return;
        const modeling = this.diagram.get<Modeling>("modeling"), factory = this.diagram.get<Factory>("elementFactory");
        if(id.startsWith("lane.")) {
            this.diagram.get<Commands>("commandStack").execute("delir.lanes",{element:el,action:id.slice(5)});return;
        }
        if (id === "connect" || id === "connect.drag") {
            this.diagram.get<{
                start: (event: Event, source: CanvasElement, autoActivate?: boolean) => void;
            }>("connect").start(event, el, id !== "connect.drag");
            return;
        }
        if (id.startsWith("append.")) {
            const target = targets.get(id.replace("append.", "create."));
            if (!target)
                return;
            const shape = factory.createShape({ ...target });
            modeling.appendShape(el, shape, { x: el.x + el.width + 100 + shape.width / 2, y: el.y + el.height / 2 }, el.parent ?? this.diagram.get<CanvasService>("canvas").getRootElement(), { connection: { type: target.type === "bpmn:TextAnnotation" ? "bpmn:Association" : "bpmn:SequenceFlow" } });
            selection.select(shape);
            return;
        }
        if (id.startsWith("replace.")) {
            const target = targets.get(id.slice(8));
            if(target?.type===el.type && (target.eventDefinitionType??"")===(el.businessObject.eventDefinitions?.[0]?.$type??""))return;
            if (target)
                modeling.updateProperties?.(el, { $type: target.type, eventDefinitions: target.eventDefinitionType ? [{ $type: target.eventDefinitionType }] : [] });
        }
    }
    private deleteSelection() {
        const selection=this.diagram.get<Selection>("selection");
        const elements=deletionTargets(selection.get(),this.diagram.get<Registry>("elementRegistry"));
        if(!elements.length)return;
        this.diagram.get<Commands>("commandStack").execute("delir.deleteSelection",{elements});
        selection.select([]);
        this.diagram.get<CanvasService>("canvas").focus();
    }
}
export default class DeliRModeler extends DeliRCanvas {
    constructor(options: {
        container: HTMLElement;
        [key: string]: unknown;
    }) { super({ ...options, editable: true }); }
}
