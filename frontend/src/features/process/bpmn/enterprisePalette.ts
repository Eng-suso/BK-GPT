
type Target = { type: string; eventDefinitionType?: string; isExpanded?: boolean };
type Entry = { id: string; group: string; icon: string; target: Target };
export const enterpriseEntries: Entry[] = [];
for (const [kind, type, definitions] of [
  ["start", "StartEvent", ["message", "timer", "conditional", "signal"]],
  ["catch", "IntermediateCatchEvent", ["message", "timer", "conditional", "signal", "link"]],
  ["throw", "IntermediateThrowEvent", ["message", "signal", "escalation", "compensate", "link"]],
  ["end", "EndEvent", ["message", "error", "escalation", "signal", "compensate", "cancel", "terminate"]],
  ["boundary", "BoundaryEvent", ["message", "timer", "conditional", "error", "escalation", "signal", "compensate", "cancel"]],
] as const) {
  for (const definition of definitions) {
    const name = definition === "compensate" ? "Compensate" : definition[0].toUpperCase() + definition.slice(1);
    const iconKind = kind === "catch" || kind === "boundary" ? "intermediate-event-catch" : kind === "throw" ? "intermediate-event-throw" : `${kind}-event`;
    enterpriseEntries.push({ id: `create.${kind}-${definition}`, group: "event", icon: `bpmn-icon-${iconKind}-${definition === "conditional" ? "condition" : definition === "compensate" ? "compensation" : definition}`, target: { type: `bpmn:${type}`, eventDefinitionType: `bpmn:${name}EventDefinition` } });
  }
}
for (const [id, type, icon] of [["user", "UserTask", "user"], ["service", "ServiceTask", "service"], ["manual", "ManualTask", "manual"], ["script", "ScriptTask", "script"], ["business-rule", "BusinessRuleTask", "business-rule"], ["send", "SendTask", "send"], ["receive", "ReceiveTask", "receive"]]) {
  enterpriseEntries.push({ id: `create.${id}-task`, group: "activity", icon: `bpmn-icon-${icon}-task`, target: { type: `bpmn:${type}` } });
}
for (const [id, type] of [["parallel", "ParallelGateway"], ["inclusive", "InclusiveGateway"], ["complex", "ComplexGateway"], ["event-based", "EventBasedGateway"]]) {
  enterpriseEntries.push({ id: `create.${id}-gateway`, group: "gateway", icon: `bpmn-icon-gateway-${id}`, target: { type: `bpmn:${type}` } });
}
enterpriseEntries.push(
  { id: "create.call-activity", group: "activity", icon: "bpmn-icon-call-activity", target: { type: "bpmn:CallActivity" } },
  { id: "create.subprocess-collapsed", group: "activity", icon: "bpmn-icon-subprocess-collapsed", target: { type: "bpmn:SubProcess", isExpanded: false } },
  { id: "create.lane", group: "collaboration", icon: "bpmn-icon-lane", target: { type: "bpmn:Lane" } },
  { id: "create.annotation", group: "artifact", icon: "bpmn-icon-text-annotation", target: { type: "bpmn:TextAnnotation" } },
);
