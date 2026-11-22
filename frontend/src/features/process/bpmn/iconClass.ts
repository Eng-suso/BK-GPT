import {enterpriseEntries} from "./enterprisePalette";

/** Catalog symbols shared by creation, replacement and the inspector. */
const symbols:Record<string,string>={
  "create.task":"task", "create.start-event":"start-event-none", "create.end-event":"end-event-none",
  "create.intermediate-event":"intermediate-event-none",
  "create.exclusive-gateway":"gateway-xor", "create.parallel-gateway":"gateway-parallel", "create.inclusive-gateway":"gateway-or",
  "create.complex-gateway":"gateway-complex", "create.event-based-gateway":"gateway-eventbased",
  "create.participant-expanded":"participant", "create.lane":"lane", "create.data-object":"data-object", "create.data-store":"data-store",
  "create.annotation":"text-annotation", "create.group":"group", "create.subprocess-expanded":"subprocess-expanded",
  "lane.add-above":"lane-insert-above", "lane.add-below":"lane-insert-below", "lane.split-2":"lane-divide-two", "lane.split-3":"lane-divide-three",
};
export function bpmnIconClass(action:string) {
  const id=action.replace(/^replace\./,"").replace(/^append\./,"create.");
  return symbols[id] ? "bpmn-icon-"+symbols[id] : enterpriseEntries.find(entry=>entry.id===id)?.icon;
}
