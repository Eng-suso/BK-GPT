import type { Project, ProjectProcess } from "@/contracts/workspace";
import type { StatusTone } from "@/components/status";

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

const PROJECT_STATUS_TONE: Record<Project["status"], StatusTone> = {
  "In corso": "ok",
  "A rischio": "warning",
  "In pausa": "pending",
  Completato: "neutral",
  Bozza: "neutral",
};

/**
 * Maps a project status to its visual status tone.
 *
 * @param status - The project status to map
 * @returns The corresponding status tone
 */
export function projectStatusTone(status: Project["status"]): StatusTone {
  return PROJECT_STATUS_TONE[status];
}

/** Sort order for the status column — most urgent first. */
const PROJECT_STATUS_RANK: Record<Project["status"], number> = {
  "A rischio": 0,
  "In corso": 1,
  "In pausa": 2,
  Bozza: 3,
  Completato: 4,
};

/**
 * Determines the sorting rank for a project status.
 *
 * @param status - The project status to rank
 * @returns The configured status rank, or `99` for an unrecognized status
 */
export function projectStatusRank(status: Project["status"]): number {
  return PROJECT_STATUS_RANK[status] ?? 99;
}
