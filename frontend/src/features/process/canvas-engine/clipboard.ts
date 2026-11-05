import { businessObject, NS, type BusinessObject } from "./types";
import type { BpmnDocument } from "./BpmnDocument";
/** Clone semantic XML independently from its SVG. Visible descendants are
 * pasted by the graph toolkit; hidden semantic descendants keep their content
 * and receive fresh identifiers. Vendor payloads remain opaque. */
export function copiedBusinessObject(type: string, data: Record<string, unknown>, id: string, sourceXml?: string, visibleIds: ReadonlySet<string> = new Set()): BusinessObject {
    const bo = businessObject(type, { ...JSON.parse(JSON.stringify(data)), id });
    if (!sourceXml)
        return bo;
    const doc = new DOMParser().parseFromString(sourceXml, "application/xml"), root = doc.documentElement;
    if (doc.querySelector("parsererror"))
        throw new Error("Impossibile copiare il contenuto XML dell'elemento.");
    for (const node of Array.from(root.getElementsByTagNameNS(NS.bpmn, "*")))
        if (visibleIds.has(node.id))
            node.remove();
    const names = new Map<string, string>([[root.id, id]]);
    for (const node of Array.from(root.getElementsByTagNameNS(NS.bpmn, "*")))
        if (node.id)
            names.set(node.id, "Copy_" + crypto.randomUUID().replaceAll("-", "").slice(0, 12));
    const refs = new Set(["sourceRef", "targetRef", "default", "attachedToRef", "dataObjectRef", "dataStoreRef", "itemSubjectRef", "activityRef"]);
    for (const node of [root, ...Array.from(root.getElementsByTagNameNS(NS.bpmn, "*"))]) {
        if (node.id && names.has(node.id))
            node.id = names.get(node.id)!;
        for (const attr of Array.from(node.attributes))
            if (refs.has(attr.localName) && names.has(attr.value))
                node.setAttributeNS(attr.namespaceURI, attr.name, names.get(attr.value)!);
        if (["incoming", "outgoing", "sourceRef", "targetRef", "flowNodeRef"].includes(node.localName) && names.has(node.textContent ?? ""))
            node.textContent = names.get(node.textContent ?? "")!;
    }
    if (type === "bpmn:Participant")
        root.removeAttribute("processRef");
    if (type === "bpmn:Group")
        root.removeAttribute("categoryValueRef");
    bo.sourceXml = new XMLSerializer().serializeToString(root);
    return bo;
}
export function sourceFragment(document: BpmnDocument | null, object: BusinessObject): string | undefined {
    const source = document?.document.getElementById(object.id);
    return source ? new XMLSerializer().serializeToString(source) : typeof object.sourceXml === "string" ? object.sourceXml : undefined;
}
