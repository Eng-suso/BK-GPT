import { businessObject, NS, type BusinessObject, type CanvasElement, type Point } from "./types";
import { enterpriseFields } from "../bpmn/enterprise";
const all = (node: ParentNode, ns: string, name: string) => Array.from((node as Document).getElementsByTagNameNS(ns, name));
const direct = (node: Element, ns: string, name: string) => Array.from(node.children).filter(child => child.namespaceURI === ns && child.localName === name);
const localType = (type: string) => { const name = type.replace(/^bpmn:/, ""); return name[0].toLowerCase() + name.slice(1); };
const number = (node: Element, name: string, fallback = 0) => { const value = Number.parseFloat(node.getAttribute(name) ?? ""); return Number.isFinite(value) ? value : fallback; };
export type ShapeRecord = {
    id: string;
    type: string;
    businessObject: BusinessObject;
    x: number;
    y: number;
    width: number;
    height: number;
    parentId?: string;
    waypoints?: Point[];
    sourceId?: string;
    targetId?: string;
    label?: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    di?: {
        get: (key: string) => string | null;
    };
};
/** The imported DOM remains the document of record. Unknown namespaces, extensions
 * and DI are retained; the editor projects only explicit modeling changes. */
export class BpmnDocument {
    readonly document: Document;
    readonly records: ShapeRecord[] = [];
    readonly rootId: string;
    readonly rootType: string;
    private baseline = "";
    private readonly originalIds = new Set<string>();
    constructor(readonly source: string) {
        this.document = new DOMParser().parseFromString(source, "application/xml");
        if (this.document.querySelector("parsererror") || this.document.documentElement.namespaceURI !== NS.bpmn || this.document.documentElement.localName !== "definitions")
            throw new Error("XML BPMN non valido.");
        const semantic = all(this.document, NS.bpmn, "*");
        const byId = new Map(semantic.filter(el => el.id).map(el => [el.id, el]));
        const activePlane = all(this.document, NS.bpmndi, "BPMNPlane")[0];
        const root = byId.get(activePlane?.getAttribute("bpmnElement") ?? "") ?? all(this.document, NS.bpmn, "collaboration")[0] ?? all(this.document, NS.bpmn, "process")[0];
        if (!root)
            throw new Error("Il documento non contiene un processo BPMN.");
        this.rootId = root.id || "DeliR_Process";
        this.rootType = "bpmn:" + root.localName[0].toUpperCase() + root.localName.slice(1);
        const poolByProcess = new Map(all(this.document, NS.bpmn, "participant").map(el => [el.getAttribute("processRef"), el.id]));
        const laneByNode = new Map<string, string>();
        for (const lane of all(this.document, NS.bpmn, "lane"))
            for (const ref of direct(lane, NS.bpmn, "flowNodeRef"))
                laneByNode.set(ref.textContent ?? "", lane.id);
        const graphical = activePlane ? [...all(activePlane, NS.bpmndi, "BPMNShape"), ...all(activePlane, NS.bpmndi, "BPMNEdge")] : [];
        for (const [index, di] of graphical.entries()) {
            const id = di.getAttribute("bpmnElement") ?? "", el = byId.get(id);
            if (!el)
                continue;
            const bounds = direct(di, NS.dc, "Bounds")[0], points = direct(di, NS.di, "waypoint");
            if (di.localName === "BPMNEdge" && points.length < 2)
                throw new Error("Il collegamento " + id + " non contiene un percorso valido.");
            const type = "bpmn:" + el.localName[0].toUpperCase() + el.localName.slice(1);
            const bo = businessObject(type, { id, name: el.localName === "textAnnotation" ? direct(el, NS.bpmn, "text")[0]?.textContent ?? "" : el.localName === "group" ? byId.get(el.getAttribute("categoryValueRef") ?? "")?.getAttribute("value") ?? "" : el.getAttribute("name") ?? "", documentation: direct(el, NS.bpmn, "documentation").map(doc => ({ text: doc.textContent ?? "" })), $attrs: Object.fromEntries(Array.from(el.attributes).filter(attr => attr.prefix && attr.prefix !== "xmlns").map(attr => [attr.name, attr.value])) });
            for (const field of enterpriseFields) {
                const value = el.getAttributeNS(NS.delir, field);
                if (value !== null)
                    bo.$attrs["delir:" + field] = value;
            }
            bo.loopKind = direct(el, NS.bpmn, "standardLoopCharacteristics").length ? "loop" : direct(el, NS.bpmn, "multiInstanceLoopCharacteristics").length ? direct(el, NS.bpmn, "multiInstanceLoopCharacteristics")[0].getAttribute("isSequential") === "true" ? "sequential" : "parallel" : undefined;
            bo.isForCompensation = el.getAttribute("isForCompensation") === "true";
            bo.isInterrupting = el.getAttribute("isInterrupting") !== "false" && el.getAttribute("cancelActivity") !== "false";
            bo.isDefaultFlow = byId.get(el.getAttribute("sourceRef") ?? "")?.getAttribute("default") === id;
            bo.hasCondition = direct(el, NS.bpmn, "conditionExpression").length > 0;
            if (el.hasAttribute("attachedToRef"))
                bo.attachedToRef = el.getAttribute("attachedToRef");
            bo.eventDefinitions = Array.from(el.children).filter(child => child.namespaceURI === NS.bpmn && child.localName.endsWith("EventDefinition")).map(child => ({ $type: "bpmn:" + child.localName[0].toUpperCase() + child.localName.slice(1) }));
            let parentId = laneByNode.get(id);
            if (!parentId) {
                let parent = el.parentElement;
                while (parent && !["process", "subProcess", "collaboration"].includes(parent.localName))
                    parent = parent.parentElement;
                if (parent?.localName === "subProcess")
                    parentId = parent.id;
                else if (parent?.localName === "process")
                    parentId = poolByProcess.get(parent.id) ?? this.rootId;
            }
            if (el.localName === "lane") {
                const owner = el.parentElement?.parentElement;
                parentId = owner?.localName === "lane" || owner?.localName === "subProcess" ? owner.id : poolByProcess.get(owner?.id ?? null) ?? this.rootId;
            }
            const labelBounds = direct(di, NS.bpmndi, "BPMNLabel")[0]?.getElementsByTagNameNS(NS.dc, "Bounds")[0];
            this.records.push({ id, type, businessObject: bo, x: bounds ? number(bounds, "x") : 100 + index * 180, y: bounds ? number(bounds, "y") : 150, width: bounds ? number(bounds, "width", 120) : 120, height: bounds ? number(bounds, "height", 80) : 80, parentId, sourceId: el.getAttribute("sourceRef") ?? direct(el, NS.bpmn, "sourceRef")[0]?.textContent ?? undefined, targetId: el.getAttribute("targetRef") ?? direct(el, NS.bpmn, "targetRef")[0]?.textContent ?? undefined, waypoints: points.length ? points.map(p => ({ x: number(p, "x"), y: number(p, "y") })) : undefined, label: labelBounds ? { x: number(labelBounds, "x"), y: number(labelBounds, "y"), width: number(labelBounds, "width", 90), height: number(labelBounds, "height", 30) } : undefined, di: { get: key => di.getAttribute(key) ?? (key.startsWith("bioc:") ? di.getAttributeNS("http://bpmn.io/schema/bpmn/biocolor/1.0", key.slice(5)) : key.startsWith("color:") ? di.getAttributeNS("http://www.omg.org/spec/BPMN/non-normative/color/1.0", key.slice(6)) : null) } });
            this.originalIds.add(id);
        }
        const shapeIds = new Set(this.records.filter(record => !record.waypoints).map(record => record.id));
        const visibleOwner = (id: string | undefined) => { let el = id ? byId.get(id) : undefined; while (el && !shapeIds.has(el.id))
            el = el.parentElement ?? undefined; return el?.id ?? id; };
        for (const record of this.records.filter(record => record.waypoints)) {
            record.sourceId = visibleOwner(record.sourceId);
            record.targetId = visibleOwner(record.targetId);
            if (!shapeIds.has(record.sourceId ?? "") || !shapeIds.has(record.targetId ?? ""))
                throw new Error("Il collegamento " + record.id + " non ha estremi rappresentabili.");
        }
        const ids = this.records.map(record => record.id);
        if (new Set(ids).size !== ids.length || ids.includes(this.rootId))
            throw new Error("Il diagramma contiene identificativi duplicati.");
    }
    setBaseline(elements: CanvasElement[]) { this.baseline = this.project(elements); }
    serialize(elements: CanvasElement[]) { const xml = this.project(elements); return xml === this.baseline ? this.source : xml; }
    private project(elements: CanvasElement[]): string {
        const doc = this.document.cloneNode(true) as Document, definitions = doc.documentElement;
        const nodes = new Map(all(doc, NS.bpmn, "*").filter(el => el.id).map(el => [el.id, el]));
        const activePlane = all(doc, NS.bpmndi, "BPMNPlane")[0];
        const shapes = new Map(activePlane ? [...all(activePlane, NS.bpmndi, "BPMNShape"), ...all(activePlane, NS.bpmndi, "BPMNEdge")].map(el => [el.getAttribute("bpmnElement"), el]) : []);
        const live = elements.filter(el => !el.labelTarget && el.type !== "label" && el.type.startsWith("bpmn:") && el.id !== this.rootId);
        const liveIds = new Set(live.map(el => el.id));
        // Remove only objects actually imported by this editor. Untouched semantic
        // objects without DI and vendor extensions are not pruned.
        for (const id of this.originalIds)
            if (!liveIds.has(id)) {
                nodes.get(id)?.remove();
                for (const di of [...all(doc, NS.bpmndi, "BPMNShape"), ...all(doc, NS.bpmndi, "BPMNEdge")])
                    if (di.getAttribute("bpmnElement") === id)
                        di.remove();
            }
        const make = (ns: string, name: string) => doc.createElementNS(ns, name);
        const appendRoot = (node:Element) => definitions.insertBefore(node,Array.from(definitions.children).find(child=>child.namespaceURI === NS.bpmndi || child.localName === "relationship") ?? null);
        const attr = (el: Element, name: string, value: unknown) => { if (value === undefined || value === null || value === "") {
            if (el.hasAttribute(name))
                el.removeAttribute(name);
        }
        else if (el.getAttribute(name) !== String(value))
            el.setAttribute(name, String(value)); };
        let process = nodes.get(this.rootId)?.localName === "process" ? nodes.get(this.rootId)! : all(doc, NS.bpmn, "process")[0];
        if (!process) {
            process = make(NS.bpmn, "bpmn:process");
            process.id = "DeliR_Process";
            appendRoot(process);
        }
        let plane = all(doc, NS.bpmndi, "BPMNPlane")[0];
        if (!plane) {
            const diagram = make(NS.bpmndi, "bpmndi:BPMNDiagram");
            diagram.id = "DeliR_Diagram";
            plane = make(NS.bpmndi, "bpmndi:BPMNPlane");
            plane.id = "DeliR_Plane";
            plane.setAttribute("bpmnElement", this.rootId);
            diagram.append(plane);
            definitions.append(diagram);
        }
        const poolProcesses = new Map<string, Element>();
        const processFor = (element: CanvasElement): Element => {
            let pool: CanvasElement | undefined = element;
            while (pool && pool.type !== "bpmn:Participant")
                pool = pool.parent;
            if (!pool)
                return process;
            const known = poolProcesses.get(pool.id);
            if (known)
                return known;
            const participant = nodes.get(pool.id);
            const reference = participant?.getAttribute("processRef");
            let scoped = reference ? nodes.get(reference) : undefined;
            if (!scoped) {
                let id = pool.id + "_process", suffix = 1;
                while (nodes.has(id))
                    id = pool.id + "_process_" + suffix++;
                scoped = make(NS.bpmn, "bpmn:process");
                scoped.id = id;
                appendRoot(scoped);
                participant?.setAttribute("processRef", id);
                nodes.set(id, scoped);
            }
            poolProcesses.set(pool.id, scoped);
            return scoped;
        };
        for (const el of live) {
            let node = nodes.get(el.id);
            const tag = localType(el.type);
            if (node && node.localName !== tag) {
                const next = make(NS.bpmn, "bpmn:" + tag);
                for (const a of Array.from(node.attributes))
                    next.setAttributeNS(a.namespaceURI, a.name, a.value);
                while (node.firstChild)
                    next.append(node.firstChild);
                node.replaceWith(next);
                node = next;
                nodes.set(el.id, node);
            }
            if (!node) {
                node = typeof el.businessObject.sourceXml === "string" ? doc.importNode(new DOMParser().parseFromString(el.businessObject.sourceXml, "application/xml").documentElement, true) : make(NS.bpmn, "bpmn:" + tag);
                if (node.localName !== tag) {
                    const replacement = make(NS.bpmn, "bpmn:" + tag);
                    for (const attr of Array.from(node.attributes))
                        replacement.setAttributeNS(attr.namespaceURI, attr.name, attr.value);
                    while (node.firstChild)
                        replacement.append(node.firstChild);
                    node = replacement;
                }
                node.id = el.id;
                const semanticParent = el.parent && nodes.get(el.parent.id);
                if (tag === "lane") {
                    const scoped = semanticParent?.localName === "lane" || semanticParent?.localName === "subProcess" ? semanticParent : processFor(el);
                    const setName = scoped.localName === "lane" ? "childLaneSet" : "laneSet";
                    let laneSet = direct(scoped, NS.bpmn, setName)[0];
                    if (!laneSet) {
                        laneSet = make(NS.bpmn, "bpmn:"+setName);
                        laneSet.id = el.id + "_lanes";
                        const anchor=Array.from(scoped.children).find(child=>child.namespaceURI === NS.bpmn && !["documentation","extensionElements","supportedInterfaceRef","ioSpecification","ioBinding","auditing","monitoring","property","laneSet"].includes(child.localName));
                        scoped.insertBefore(laneSet,anchor ?? null);
                    }
                    laneSet.append(node);
                }
                else if (tag === "participant") {
                    let collaboration = all(doc, NS.bpmn, "collaboration")[0];
                    if (!collaboration) {
                        collaboration = make(NS.bpmn, "bpmn:collaboration");
                        collaboration.id = this.rootId + "_collaboration";
                        while(nodes.has(collaboration.id)) collaboration.id += "_1";
                        nodes.set(collaboration.id,collaboration);
                        plane.setAttribute("bpmnElement",collaboration.id);
                        appendRoot(collaboration);
                    }
                    collaboration.append(node);
                }
                else if (tag === "messageFlow") {
                    const collaboration = all(doc, NS.bpmn, "collaboration")[0];
                    if (!collaboration) throw new Error("Un flusso messaggio richiede una collaborazione.");
                    collaboration.append(node);
                } else
                    (semanticParent?.localName === "subProcess" ? semanticParent : processFor(el)).append(node);
                nodes.set(el.id, node);
            }
            if (tag === "participant")
                processFor(el);
            if (tag === "textAnnotation") {
                let value = direct(node, NS.bpmn, "text")[0];
                if (!value) {
                    value = make(NS.bpmn, "bpmn:text");
                    node.append(value);
                }
                if (value.textContent !== el.businessObject.name)
                    value.textContent = el.businessObject.name ?? "";
            }
            else if (tag === "group") {
                let categoryValue = nodes.get(node.getAttribute("categoryValueRef") ?? "");
                if (!categoryValue) {
                    const category = make(NS.bpmn, "bpmn:category");
                    category.id = el.id + "_category";
                    categoryValue = make(NS.bpmn, "bpmn:categoryValue");
                    categoryValue.id = el.id + "_value";
                    category.append(categoryValue);
                    appendRoot(category);
                    node.setAttribute("categoryValueRef", categoryValue.id);
                    nodes.set(categoryValue.id, categoryValue);
                }
                attr(categoryValue, "value", el.businessObject.name);
            }
            else
                attr(node, "name", el.businessObject.name);
            if (tag === "dataObjectReference" && !node.hasAttribute("dataObjectRef")) {
                const object = make(NS.bpmn, "bpmn:dataObject");
                object.id = el.id + "_object";
                processFor(el).append(object);
                node.setAttribute("dataObjectRef", object.id);
            }
            if (tag === "dataStoreReference" && !node.hasAttribute("dataStoreRef")) {
                const store = make(NS.bpmn, "bpmn:dataStore");
                store.id = el.id + "_store";
                appendRoot(store);
                node.setAttribute("dataStoreRef", store.id);
            }
            if (el.host)
                attr(node, "attachedToRef", el.host.id);
            if (el.waypoints && !/Data(Input|Output)Association$/.test(el.type)) {
                attr(node, "sourceRef", el.source?.id);
                attr(node, "targetRef", el.target?.id);
            }
            const notes = el.businessObject.documentation;
            if (notes) {
                const docs = direct(node, NS.bpmn, "documentation");
                if (notes.map(n => n.text ?? "").join("\n") !== docs.map(d => d.textContent ?? "").join("\n")) {
                    docs.forEach(d => d.remove());
                    for (const note of notes) {
                        const d = make(NS.bpmn, "bpmn:documentation");
                        d.textContent = note.text ?? "";
                        node.prepend(d);
                    }
                }
            }
            for (const field of enterpriseFields) {
                const key = "delir:" + field, value = el.businessObject.$attrs[key];
                if (value !== undefined && value !== null && value !== "") {
                    definitions.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:delir", NS.delir);
                    node.setAttributeNS(NS.delir, key, String(value));
                }
                else
                    node.removeAttributeNS(NS.delir, field);
            }
            const eventDefinitions = el.businessObject.eventDefinitions;
            if (eventDefinitions && eventDefinitions.map(d => localType(d.$type)).join() !== Array.from(node.children).filter(c => c.namespaceURI === NS.bpmn && c.localName.endsWith("EventDefinition")).map(c => c.localName).join()) {
                Array.from(node.children).filter(c => c.localName.endsWith("EventDefinition")).forEach(c => c.remove());
                for (const definition of eventDefinitions)
                    node.append(make(NS.bpmn, "bpmn:" + localType(definition.$type)));
            }
            let di = shapes.get(el.id);
            if (!di) {
                di = make(NS.bpmndi, el.waypoints ? "bpmndi:BPMNEdge" : "bpmndi:BPMNShape");
                di.id = el.id + "_di";
                di.setAttribute("bpmnElement", el.id);
                plane.append(di);
            }
            if (el.waypoints) {
                const old = direct(di, NS.di, "waypoint"), anchor = old.at(-1)?.nextSibling ?? direct(di, NS.bpmndi, "BPMNLabel")[0] ?? null;
                old.forEach(p => p.remove());
                for (const point of el.waypoints) {
                    const p = make(NS.di, "di:waypoint");
                    attr(p, "x", point.x);
                    attr(p, "y", point.y);
                    di.insertBefore(p, anchor);
                }
            }
            else {
                let bounds = direct(di, NS.dc, "Bounds")[0];
                if (!bounds) {
                    bounds = make(NS.dc, "dc:Bounds");
                    di.prepend(bounds);
                }
                for (const key of ["x", "y", "width", "height"] as const)
                    attr(bounds, key, el[key]);
            }
            const label = elements.find(item => item.labelTarget?.id === el.id);
            if (label) {
                let labelNode = direct(di, NS.bpmndi, "BPMNLabel")[0];
                if (!labelNode) {
                    labelNode = make(NS.bpmndi, "bpmndi:BPMNLabel");
                    di.append(labelNode);
                }
                let bounds = direct(labelNode, NS.dc, "Bounds")[0];
                if (!bounds) {
                    bounds = make(NS.dc, "dc:Bounds");
                    labelNode.append(bounds);
                }
                for (const key of ["x", "y", "width", "height"] as const)
                    attr(bounds, key, label[key]);
            }
        }
        const laneByNode = new Map(live.filter(el => el.parent?.type === "bpmn:Lane" && !el.waypoints && !["bpmn:Lane", "bpmn:Participant"].includes(el.type)).map(el => [el.id, el.parent!.id]));
        for (const lane of all(doc, NS.bpmn, "lane"))
            for (const ref of direct(lane, NS.bpmn, "flowNodeRef"))
                if (this.originalIds.has(ref.textContent ?? "") && laneByNode.get(ref.textContent ?? "") !== lane.id)
                    ref.remove();
        for (const [id, laneId] of laneByNode) {
            const lane = nodes.get(laneId);
            if (lane && !direct(lane, NS.bpmn, "flowNodeRef").some(ref => ref.textContent === id)) {
                const ref = make(NS.bpmn, "bpmn:flowNodeRef");
                ref.textContent = id;
                lane.insertBefore(ref,direct(lane,NS.bpmn,"childLaneSet")[0] ?? null);
            }
        }
        const flowEndpoints = new Map(live.filter(el => el.waypoints).map(el => [el.id, { source: el.source?.id, target: el.target?.id }]));
        for (const node of all(doc, NS.bpmn, "*")) {
            if (node.localName === "incoming" || node.localName === "outgoing") {
                const endpoint = flowEndpoints.get(node.textContent ?? "");
                if (endpoint && node.parentElement?.id !== (node.localName === "incoming" ? endpoint.target : endpoint.source))
                    node.remove();
            }
            const defaultFlow = node.getAttribute("default");
            if (defaultFlow && this.originalIds.has(defaultFlow) && !liveIds.has(defaultFlow))
                node.removeAttribute("default");
        }
        // Referential integrity after structural edits; conditions and arbitrary
        // extension elements on surviving flows are left intact.
        for (const node of all(doc, NS.bpmn, "*")) {
            if (node.localName === "incoming" || node.localName === "outgoing" || node.localName === "flowNodeRef") {
                const id = node.textContent ?? "";
                if (this.originalIds.has(id) && !liveIds.has(id))
                    node.remove();
            }
        }
        for (const el of live.filter(el => el.waypoints && el.type === "bpmn:SequenceFlow"))
            for (const [key, endpoint] of [["outgoing", el.source], ["incoming", el.target]] as const) {
                const node = endpoint && nodes.get(endpoint.id);
                if (node && !direct(node, NS.bpmn, key).some(ref => ref.textContent === el.id)) {
                    const ref = make(NS.bpmn, "bpmn:" + key);
                    ref.textContent = el.id;
                    const before=Array.from(node.children).find(child=>child.namespaceURI === NS.bpmn && (key === "incoming" && child.localName === "outgoing" || !["documentation","extensionElements","auditing","monitoring","categoryValueRef","incoming","outgoing"].includes(child.localName)));
                    node.insertBefore(ref,before ?? null);
                }
            }
        return new XMLSerializer().serializeToString(doc);
    }
}
