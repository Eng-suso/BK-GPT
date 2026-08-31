import { createContext, useContext } from "react";

import type { Project, ProjectProcess } from "../../../contracts/workspace";
import type { SimulationRun } from "./simulationTypes";

export type SimulationSectionValue = {
  projectId: string;
  processId: string;
  project: Project;
  process: ProjectProcess;
  /** Saved BPMN of the model (the section has no live canvas mounted). */
  bpmnXml: string | null;
  runs: SimulationRun[];
  runsLoading: boolean;
  refetchRuns: () => void;
};

export const SimulationSectionContext =
  createContext<SimulationSectionValue | null>(null);

export function useSimulationSection(): SimulationSectionValue {
  const ctx = useContext(SimulationSectionContext);
  if (!ctx) {
    throw new Error("useSimulationSection must be used within <SimulationLayout>");
  }
  return ctx;
}

/** "{scenario} · 14 mar 10:32" — scenario names collide, dates disambiguate. */
export function formatRunOption(run: SimulationRun, lang: "it" | "en"): string {
  const when = new Date(run.created_at);
  const date = Number.isNaN(when.getTime())
    ? ""
    : ` · ${when.toLocaleString(lang === "it" ? "it-IT" : "en-US", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })}`;
  return `${run.scenario_name}${date}`;
}

/**
 * Resolve which run a run-scoped page should show: the `:runId` from the URL when
 * valid, otherwise the newest completed run, otherwise the newest run.
 */
export function resolveActiveRun(
  runs: SimulationRun[],
  runIdParam: string | undefined,
): SimulationRun | null {
  const id = runIdParam ? Number(runIdParam) : Number.NaN;
  if (Number.isFinite(id)) {
    return runs.find((run) => run.id === id) ?? null;
  }
  return runs.find((run) => run.status === "completed") ?? runs[0] ?? null;
}
