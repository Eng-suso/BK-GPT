import type { BpmnElementSelection, SelectedBpmnElement } from "./types";
import { splitTraceability } from "./provenance";

export const enterpriseFields = ["owner", "office", "required", "rules", "risks", "sop", "inputs", "outputs", "systems", "files"] as const;
export type EnterpriseField = typeof enterpriseFields[number];
export type EnterpriseMetadata = Record<Exclude<EnterpriseField, "required">, string> & { required: boolean };

/** Namespaced BPMN attributes travel with save, export, import and undo/redo. */
export const enterpriseModdle = {
  name: "DeliR", uri: "https://delir.app/schema/bpmn/1.0", prefix: "delir",
  types: [{ name: "EnterpriseProperties", extends: ["bpmn:BaseElement"], properties: enterpriseFields.map(name => ({ name, type: name === "required" ? "Boolean" : "String", isAttr: true })) }],
};

export function readSelectedElement(element: BpmnElementSelection): SelectedBpmnElement {
  const bo = element.businessObject;
  const metadata = Object.fromEntries(enterpriseFields.map(field => {
    const value = bo?.get?.(`delir:${field}`) ?? bo?.$attrs?.[`delir:${field}`];
    return [field, field === "required" ? value === true || value === "true" : typeof value === "string" ? value : ""];
  })) as EnterpriseMetadata;
  return { id: element.id, type: element.type.replace(/^bpmn:/, ""), name: bo?.name ?? "", documentation: splitTraceability(bo?.documentation?.[0]?.text).notes, metadata };
}
