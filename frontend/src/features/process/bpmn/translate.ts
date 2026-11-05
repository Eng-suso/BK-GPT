import { i18n } from "@/lib/i18n";

const ACTION_LABELS: Record<string, string> = {
  "Delete": "delete",
  "Change element": "replace",
  "Connect to other element": "connect",
  "Connect using association": "association",
  "Connect using data input association": "dataAssociation",
  "Append task": "task",
  "Append receive task": "receive",
  "Append end event": "end",
  "Append gateway": "gateway",
  "Append intermediate/boundary event": "event",
  "Add text annotation": "annotation",
  "Add lane above": "laneAbove",
  "Add lane below": "laneBelow",
  "Divide into two lanes": "twoLanes",
  "Divide into three lanes": "threeLanes",
  "Append message intermediate catch event": "message",
  "Append timer intermediate catch event": "timer",
  "Append conditional intermediate catch event": "condition",
  "Append signal intermediate catch event": "signal",
  "Append compensation activity": "compensation"
};

const LABELS: Record<string, string> = {
  "General": "general",
  "Documentation": "documentation",
  "Name": "name",
  "ID": "id",
  "Executable": "executable",
  "Process": "process",
  "Participant": "participant",
  "User Task": "userTask",
  "Service Task": "serviceTask",
  "Task": "task",
  "Start Event": "start",
  "End Event": "end",
  "Exclusive Gateway": "gateway",
  "Lane": "lane",
  "Toggle section": "toggleSection",
  "Add documentation": "addDocumentation",
  "No element selected": "noSelection"
};

/** Localize provider labels, leaving BPMN names and unknown extension strings intact. */
export function translateBpmnLabel(template: string, replacements?: Record<string, string | number>): string {
  const action = ACTION_LABELS[template];
  if (action) return i18n.t("process:canvas.context." + action);
  const key = LABELS[template];
  const label = key ? i18n.t(`process:properties.vendor.${key}`, { defaultValue: template }) : template;
  return label.replace(/\{([^}]+)\}/g, (match, name: string) => replacements?.[name] === undefined ? match : String(replacements[name]));
}
