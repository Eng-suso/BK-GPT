import type { AgentActivity } from "../types";

const AGENT_ACTIVITY_LABELS: Record<string, string> = {
  canvas_subgraph: "Apro canvas",
  canvas_router: "Scelgo percorso",
  canvas_macro_agent: "Coordino canvas",
  patch_edit_subgraph: "Preparo modifica",
  canvas_patch_edit_agent: "Modifico elementi",
  construction_subgraph: "Preparo modello",
  canvas_construction_agent: "Costruisco processo",
  layout_subgraph: "Preparo disegno",
  canvas_layout_consultant_agent: "Studio layout",
  canvas_drawing_agent: "Disegno canvas",
  validation_subgraph: "Verifico canvas",
  canvas_validation_agent: "Controllo copertura",
  evaluate_canvas_completion: "Valuto completamento",
  canvas_completion_report: "Chiudo risultato",
  ask_canvas_clarification: "Preparo domanda",
};

export function activityLabelForNode(nodeName: string): string {
  const label = AGENT_ACTIVITY_LABELS[nodeName] || nodeName.replace(/_/g, " ");
  return label.split(/\s+/).slice(0, 5).join(" ");
}

const AGENT_ACTIVITY_ICONS: Record<string, string> = {
  canvas_subgraph: "layout",
  canvas_router: "route",
  canvas_macro_agent: "brain",
  patch_edit_subgraph: "edit",
  canvas_patch_edit_agent: "edit",
  construction_subgraph: "build",
  canvas_construction_agent: "build",
  layout_subgraph: "compass",
  canvas_layout_consultant_agent: "compass",
  canvas_drawing_agent: "draw",
  validation_subgraph: "check",
  canvas_validation_agent: "check",
  evaluate_canvas_completion: "check",
  canvas_completion_report: "check",
  ask_canvas_clarification: "help",
};

export function activityIconForNode(nodeName: string): string {
  return AGENT_ACTIVITY_ICONS[nodeName] || "brain";
}

/** Advance the activity list: mark the running step done, start `nodeName`. */
export function nextAgentActivity(
  current: AgentActivity[] | undefined,
  nodeName: string,
  label?: string,
  icon?: string,
): AgentActivity[] {
  const existing = current || [];
  const completed = existing.map((item) =>
    item.status === "running" ? { ...item, status: "completed" as const } : item,
  );
  const previousIndex = completed.findIndex((item) => item.key === nodeName);
  const nextItem: AgentActivity = {
    key: nodeName,
    label: (label || activityLabelForNode(nodeName)).split(/\s+/).slice(0, 5).join(" "),
    status: "running",
    icon: icon || activityIconForNode(nodeName),
  };

  if (previousIndex >= 0) {
    const updated = [...completed];
    updated[previousIndex] = nextItem;
    return updated;
  }

  return [...completed, nextItem];
}

export function completeAgentActivity(
  current: AgentActivity[] | undefined,
): AgentActivity[] | undefined {
  if (!current || current.length === 0) return current;
  return current.map((item) => ({ ...item, status: "completed" }));
}
