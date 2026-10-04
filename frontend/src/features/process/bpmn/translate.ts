import { i18n } from "@/lib/i18n";

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
  const key = LABELS[template];
  const label = key ? i18n.t(`process:properties.vendor.${key}`, { defaultValue: template }) : template;
  return label.replace(/\{([^}]+)\}/g, (match, name: string) => replacements?.[name] === undefined ? match : String(replacements[name]));
}
