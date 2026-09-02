import type { AgentActivity } from "../types";

const AGENT_ACTIVITY_LABELS: Record<string, string> = {
  canvas_subgraph: "Apro il contesto canvas",
  canvas_router: "Scelgo il percorso operativo",
  canvas_macro_agent: "Coordino il lavoro sul canvas",
  patch_edit_subgraph: "Eseguo la modifica locale",
  canvas_patch_edit_agent: "Aggiorno gli elementi del canvas",
  construction_subgraph: "Preparo la costruzione del canvas",
  canvas_construction_agent: "Genero o revisiono il modello",
  layout_subgraph: "Preparo il disegno del canvas",
  canvas_drawing_agent: "Ridisegno elementi e collegamenti",
  validation_subgraph: "Verifico il canvas",
  canvas_validation_agent: "Controllo struttura e copertura",
  evaluate_canvas_completion: "Valuto se la richiesta e' completa",
  canvas_completion_report: "Chiudo con il risultato verificato",
  ask_canvas_clarification: "Preparo una domanda di chiarimento",
};

export function activityLabelForNode(nodeName: string): string {
  return AGENT_ACTIVITY_LABELS[nodeName] || nodeName.replace(/_/g, " ");
}

/** Advance the activity list: mark the running step done, start `nodeName`. */
export function nextAgentActivity(
  current: AgentActivity[] | undefined,
  nodeName: string,
): AgentActivity[] {
  const existing = current || [];
  const completed = existing.map((item) =>
    item.status === "running" ? { ...item, status: "completed" as const } : item,
  );
  const previousIndex = completed.findIndex((item) => item.key === nodeName);
  const nextItem: AgentActivity = {
    key: nodeName,
    label: activityLabelForNode(nodeName),
    status: "running",
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
