import type { Project, ProjectProcess } from "@/contracts/workspace";

export type { Project, ProjectProcess };

/** Tabs on the project detail page — every entry has a working backend. */
export type ProjectTab = {
  id: string;
  labelKey: string;
};

export const PROJECT_TABS: ProjectTab[] = [
  { id: "overview", labelKey: "detail.tabs.overview" },
  { id: "chat", labelKey: "detail.tabs.chat" },
  { id: "processes", labelKey: "detail.tabs.processes" },
  { id: "sources", labelKey: "detail.tabs.sources" },
  { id: "decisions", labelKey: "detail.tabs.decisions" },
];

export const PROJECT_TAB_IDS = PROJECT_TABS.map((tab) => tab.id);

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

/** Sort order for the status column — most urgent first. */
const PROJECT_STATUS_RANK: Record<Project["status"], number> = {
  "A rischio": 0,
  "In corso": 1,
  Bozza: 2,
};

export function projectStatusRank(status: Project["status"]): number {
  return PROJECT_STATUS_RANK[status] ?? 99;
}
