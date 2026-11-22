import type { CanvasElement } from "./types";

export function participant(element: CanvasElement | undefined): CanvasElement | undefined {
  while (element && element.type !== "bpmn:Participant") element = element.parent;
  return element;
}
export function flowScope(element: CanvasElement | undefined): CanvasElement | undefined {
  while (element && !/Process$|Participant$|SubProcess$|Collaboration$/.test(element.type)) element = element.parent;
  return element;
}
const activity = (element: CanvasElement) => /Task$|Activity$|SubProcess$/.test(element.type);
const messageEvent = (element: CanvasElement) => element.businessObject.eventDefinitions?.some(def => def.$type === "bpmn:MessageEventDefinition");
const messageSource = (element: CanvasElement) => activity(element) || element.type === "bpmn:Participant" || Boolean(messageEvent(element) && /IntermediateThrowEvent$|EndEvent$/.test(element.type));
const messageTarget = (element: CanvasElement) => activity(element) || element.type === "bpmn:Participant" || Boolean(messageEvent(element) && /StartEvent$|IntermediateCatchEvent$|BoundaryEvent$/.test(element.type));
const flowNode = (element: CanvasElement) => activity(element) || /Event$|Gateway$/.test(element.type);

/** OMG BPMN 2.0.2 §7.6, §9.3: lanes are partitions, never flow endpoints. */
export function connectionRule(source?: CanvasElement, target?: CanvasElement): false | { type: string } {
  if (!source || !target || source === target || source.labelTarget || target.labelTarget || source.waypoints || target.waypoints) return false;
  if (/Lane$|Group$|Process$|Collaboration$/.test(source.type) || /Lane$|Group$|Process$|Collaboration$/.test(target.type)) return false;
  if (/TextAnnotation$|DataObjectReference$|DataStoreReference$/.test(source.type) || /TextAnnotation$|DataObjectReference$|DataStoreReference$/.test(target.type)) return { type: "bpmn:Association" };
  const from = participant(source), to = participant(target);
  if (from !== to) return from && to && messageSource(source) && messageTarget(target) ? { type: "bpmn:MessageFlow" } : false;
  if (!flowNode(source) || !flowNode(target) || flowScope(source.parent) !== flowScope(target.parent)) return false;
  if (/EndEvent$/.test(source.type) || /StartEvent$|BoundaryEvent$/.test(target.type)) return false;
  return { type: "bpmn:SequenceFlow" };
}

export function canStartConnection(source?: CanvasElement): boolean {
  return Boolean(source && !source.labelTarget && !source.waypoints && (flowNode(source) && !/EndEvent$/.test(source.type) || messageSource(source) || /TextAnnotation$|DataObjectReference$|DataStoreReference$/.test(source.type)));
}
