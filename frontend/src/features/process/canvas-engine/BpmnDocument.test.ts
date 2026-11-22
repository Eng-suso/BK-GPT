import { describe, expect, it } from "vitest";
import { BpmnDocument } from "./BpmnDocument";
import { businessObject, NS, type CanvasElement } from "./types";
const xml = '<?xml version="1.0" encoding="UTF-8"?>\n<!-- retained source -->\n<bpmn:definitions xmlns:bpmn="' + NS.bpmn + '" xmlns:bpmndi="' + NS.bpmndi + '" xmlns:dc="' + NS.dc + '" xmlns:di="' + NS.di + '" xmlns:delir="' + NS.delir + '" xmlns:vendor="urn:vendor" targetNamespace="urn:contract"><bpmn:process id="process" isExecutable="false"><bpmn:startEvent id="start"/><bpmn:userTask id="task" name="Verify" delir:owner="Operations" vendor:flag="keep"><bpmn:extensionElements><vendor:payload mode="strict"><vendor:item>opaque data</vendor:item></vendor:payload></bpmn:extensionElements><bpmn:documentation><![CDATA[notes & traceability]]></bpmn:documentation><bpmn:incoming>flow</bpmn:incoming></bpmn:userTask><bpmn:sequenceFlow id="flow" sourceRef="start" targetRef="task"><bpmn:conditionExpression><![CDATA[amount > 10 && approved]]></bpmn:conditionExpression></bpmn:sequenceFlow></bpmn:process><bpmndi:BPMNDiagram id="diagram"><bpmndi:BPMNPlane id="plane" bpmnElement="process"><bpmndi:BPMNShape id="start_di" bpmnElement="start"><dc:Bounds x="20" y="40" width="36" height="36"/></bpmndi:BPMNShape><bpmndi:BPMNShape id="task_di" bpmnElement="task" vendor:style="keep"><dc:Bounds x="150" y="20" width="160" height="88"/></bpmndi:BPMNShape><bpmndi:BPMNEdge id="flow_di" bpmnElement="flow"><di:waypoint x="56" y="58"/><di:waypoint x="150" y="58"/></bpmndi:BPMNEdge></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>';
function importDocument(source = xml) {
    const doc = new BpmnDocument(source);
    const elements = doc.records.map(record => ({ ...record })) as unknown as CanvasElement[];
    for (const element of elements) {
        const record = doc.records.find(r => r.id === element.id)!;
        if (record.sourceId)
            element.source = elements.find(el => el.id === record.sourceId);
        if (record.targetId)
            element.target = elements.find(el => el.id === record.targetId);
    }
    doc.setBaseline(elements);
    return { doc, elements };
}
const parse = (source: string) => new DOMParser().parseFromString(source, "application/xml");
describe("DeliR BPMN document contract", () => {
    it("returns the exact source, including prolog and comments, for navigation and an undone edit", () => {
        const { doc, elements } = importDocument();
        expect(doc.serialize(elements)).toBe(xml);
        const task = elements.find(el => el.id === "task")!;
        task.businessObject.name = "Renamed";
        expect(doc.serialize(elements)).not.toBe(xml);
        task.businessObject.name = "Verify";
        expect(doc.serialize(elements)).toBe(xml);
    });
    it("edits name, geometry and enterprise metadata without losing vendor extensions, conditions, IDs or DI attributes", () => {
        const { doc, elements } = importDocument();
        const task = elements.find(el => el.id === "task")!;
        task.businessObject.name = "Checked";
        task.x += 25;
        task.businessObject.$attrs["delir:owner"] = "Finance";
        const saved = parse(doc.serialize(elements));
        expect(saved.querySelector("parsererror")).toBeNull();
        const node = saved.getElementById("task")!;
        expect(node.getAttribute("name")).toBe("Checked");
        expect(node.getAttributeNS(NS.delir, "owner")).toBe("Finance");
        expect(node.getAttributeNS("urn:vendor", "flag")).toBe("keep");
        expect(saved.getElementsByTagNameNS("urn:vendor", "item")[0].textContent).toBe("opaque data");
        expect(saved.getElementsByTagNameNS(NS.bpmn, "conditionExpression")[0].textContent).toBe("amount > 10 && approved");
        expect(saved.getElementById("task_di")!.getAttributeNS("urn:vendor", "style")).toBe("keep");
        expect(saved.getElementById("task_di")!.getElementsByTagNameNS(NS.dc, "Bounds")[0].getAttribute("x")).toBe("175");
        const flow = saved.getElementById("flow")!;
        expect(flow.getAttribute("sourceRef")).toBe("start");
        expect(flow.getAttribute("targetRef")).toBe("task");
        expect(Array.from(saved.getElementById("flow_di")!.getElementsByTagNameNS(NS.di, "waypoint")).map(p => p.getAttribute("x"))).toEqual(["56", "150"]);
    });
    it("removes deleted graph references and restores the original XML when the command is undone", () => {
        const { doc, elements } = importDocument();
        const kept = elements.filter(el => !["task", "flow"].includes(el.id));
        const saved = parse(doc.serialize(kept));
        expect(saved.getElementById("task")).toBeNull();
        expect(saved.getElementById("flow")).toBeNull();
        expect(saved.getElementById("task_di")).toBeNull();
        expect(saved.getElementById("start")).not.toBeNull();
        expect(doc.serialize(elements)).toBe(xml);
    });
    it("changes only the active DI plane while preserving alternate layouts", () => {
        const alternate = '<bpmndi:BPMNDiagram id="alternate"><bpmndi:BPMNPlane id="alternate_plane" bpmnElement="process"><bpmndi:BPMNShape id="alternate_task_di" bpmnElement="task"><dc:Bounds x="900" y="800" width="160" height="88"/></bpmndi:BPMNShape></bpmndi:BPMNPlane></bpmndi:BPMNDiagram>';
        const { doc, elements } = importDocument(xml.replace("</bpmn:definitions>", alternate + "</bpmn:definitions>"));
        expect(doc.records).toHaveLength(3);
        elements.find(el => el.id === "task")!.x = 175;
        const saved = parse(doc.serialize(elements));
        expect(saved.getElementById("alternate_task_di")!.getElementsByTagNameNS(NS.dc, "Bounds")[0].getAttribute("x")).toBe("900");
        expect(saved.getElementById("task_di")!.getElementsByTagNameNS(NS.dc, "Bounds")[0].getAttribute("x")).toBe("175");
    });
    it("updates incoming and outgoing references when a connection is reattached", () => {
        const { doc, elements } = importDocument();
        const next = { ...elements.find(el => el.id === "task")!, id: "next", businessObject: businessObject("bpmn:UserTask", { id: "next", name: "Next" }) };
        const flow = elements.find(el => el.id === "flow")!;
        flow.target = next;
        const saved = parse(doc.serialize([...elements, next]));
        expect(saved.getElementById("task")!.getElementsByTagNameNS(NS.bpmn, "incoming")).toHaveLength(0);
        expect(saved.getElementById("next")!.getElementsByTagNameNS(NS.bpmn, "incoming")[0].textContent).toBe("flow");
        expect(saved.getElementById("flow")!.getAttribute("targetRef")).toBe("next");
    });
    it("creates the semantic definitions required by data references and groups", () => {
        const { doc, elements } = importDocument(), base = elements.find(el => el.id === "task")!;
        const extra = ["DataObjectReference", "DataStoreReference", "Group"].map((type, index) => ({ ...base, id: "new_" + index, type: "bpmn:" + type, businessObject: businessObject("bpmn:" + type, { id: "new_" + index, name: "Information" }) }));
        const saved = parse(doc.serialize([...elements, ...extra]));
        expect(saved.getElementById(saved.getElementById("new_0")!.getAttribute("dataObjectRef")!)).not.toBeNull();
        expect(saved.getElementById(saved.getElementById("new_1")!.getAttribute("dataStoreRef")!)).not.toBeNull();
        expect(saved.getElementById(saved.getElementById("new_2")!.getAttribute("categoryValueRef")!)!.getAttribute("value")).toBe("Information");
    });

    it("creates independent participant processes and collaboration-owned message flows with unique IDs", () => {
        const {doc,elements}=importDocument();
        const root={id:"process",type:"bpmn:Process"} as CanvasElement;
        const pool=(id:string,x:number):CanvasElement=>({id,type:"bpmn:Participant",businessObject:businessObject("bpmn:Participant",{id,name:id}),parent:root,x,y:250,width:500,height:200});
        const first=pool("Company",20),second=pool("Partner",650);
        const flow:CanvasElement={id:"Message",type:"bpmn:MessageFlow",businessObject:businessObject("bpmn:MessageFlow",{id:"Message"}),source:first,target:second,x:0,y:0,width:0,height:0,waypoints:[{x:520,y:350},{x:650,y:350}]};
        const saved=parse(doc.serialize([...elements,first,second,flow]));
        const ids=Array.from(saved.querySelectorAll("[id]")).map(node=>node.id);
        expect(new Set(ids).size).toBe(ids.length);
        const collaboration=saved.getElementsByTagNameNS(NS.bpmn,"collaboration")[0];
        expect(collaboration.id).not.toBe("process");
        expect(saved.getElementById("Message")!.parentElement).toBe(collaboration);
        expect(saved.getElementById(saved.getElementById("Company")!.getAttribute("processRef")!)).not.toBeNull();
        expect(saved.getElementById("Company")!.getAttribute("processRef")).not.toBe(saved.getElementById("Partner")!.getAttribute("processRef"));
        expect(saved.getElementById("plane")!.getAttribute("bpmnElement")).toBe(collaboration.id);
        expect(new BpmnDocument(new XMLSerializer().serializeToString(saved)).records.filter(record=>record.type === "bpmn:MessageFlow")).toHaveLength(1);
    });
    it("rejects malformed or unrelated XML instead of replacing it with an empty diagram", () => {
        expect(() => new BpmnDocument("<broken")).toThrow();
        expect(() => new BpmnDocument("<definitions/>")).toThrow();
    });
    it("transfers existing nodes and internal flows into a pool process without losing payloads",()=>{
        const {doc,elements}=importDocument();
        const root={id:"process",type:"bpmn:Process"} as CanvasElement;
        const pool:CanvasElement={id:"Pool",type:"bpmn:Participant",parent:root,businessObject:businessObject("bpmn:Participant",{id:"Pool"}),x:0,y:0,width:600,height:400};
        for(const el of elements)el.parent=pool;
        const saved=parse(doc.serialize([...elements,pool]));
        const processId=saved.getElementById("Pool")!.getAttribute("processRef")!;
        for(const id of ["start","task","flow"])expect(saved.getElementById(id)!.parentElement!.id).toBe(processId);
        expect(saved.getElementsByTagNameNS("urn:vendor","item")[0].textContent).toBe("opaque data");
        expect(saved.getElementsByTagNameNS(NS.bpmn,"conditionExpression")[0].textContent).toBe("amount > 10 && approved");
        const reloaded=new BpmnDocument(new XMLSerializer().serializeToString(saved));
        expect(reloaded.records.filter(r=>r.id!=="Pool").every(r=>r.parentId==="Pool")).toBe(true);
        for(const el of elements)delete el.parent;
        expect(doc.serialize(elements)).toBe(xml);
    });
});
