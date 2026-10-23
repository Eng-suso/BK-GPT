/**
 * SIM-06b: il log simulato di un run, da scaricare in CSV o XES.
 *
 * Il backend lo esporta come event log canonico (#92); lo scenario del
 * workspace e la sua revisione stanno nel nome del file, nelle intestazioni e,
 * per l'XES, nei metadati del log.
 */
import { httpBlob } from "@/lib/http";

import type { SimulationRun } from "./simulationTypes";

export type RunLogFormat = "csv" | "xes";

/** Il nome che usa anche il backend: `simulation-run-42-scenario-3-rev-5.csv`. */
export function runLogFilename(run: Pick<SimulationRun, "id" | "request">, format: RunLogFormat): string {
  const ref = (run.request as { workspace_scenario?: { id?: unknown; revision?: unknown } } | null)?.workspace_scenario;
  const scenario = ref && typeof ref.id === "number" && typeof ref.revision === "number" ? `-scenario-${ref.id}-rev-${ref.revision}` : "";
  return `simulation-run-${run.id}${scenario}.${format}`;
}

export async function downloadRunLog(run: Pick<SimulationRun, "id" | "request">, format: RunLogFormat): Promise<void> {
  const blob = await httpBlob(`/v1/workspace/simulation-runs/${run.id}/event-log?format=${format}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = runLogFilename(run, format);
  link.click();
  URL.revokeObjectURL(url);
}
