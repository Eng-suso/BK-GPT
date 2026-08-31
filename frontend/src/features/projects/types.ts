import type { Project, ProjectProcess } from "@/contracts/workspace";

export type { Project, ProjectProcess };

/** Tabs on the project detail page. `available: false` = no backend yet. */
export type ProjectTab = {
  id: string;
  labelKey: string;
  available: boolean;
};

export const PROJECT_TABS: ProjectTab[] = [
  { id: "overview", labelKey: "detail.tabs.overview", available: true },
  { id: "chat", labelKey: "detail.tabs.chat", available: true },
  { id: "processes", labelKey: "detail.tabs.processes", available: true },
  { id: "sources", labelKey: "detail.tabs.sources", available: true },
  { id: "decisions", labelKey: "detail.tabs.decisions", available: true },
  { id: "analysis", labelKey: "detail.tabs.analysis", available: false },
  { id: "kpi", labelKey: "detail.tabs.kpi", available: false },
  { id: "team", labelKey: "detail.tabs.team", available: false },
];

const PROJECT_STATUS_TONE = {
  "In corso": "ok",
  "A rischio": "warning",
  Bozza: "neutral",
} as const;

export function projectStatusTone(
  status: Project["status"],
): "ok" | "warning" | "neutral" {
  return PROJECT_STATUS_TONE[status];
}
