import React from "react";
import { useTranslation } from "react-i18next";

import { latestMappedLog, realProcessingByElement } from "./eventlog/realVsSimulated";
import { useEventLogAnalysis, useEventLogs } from "./eventlog/useEventLogImport";
import { sourceConflicts, type SourceConflict } from "./sourceConflicts";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationClaims } from "./simulationTypes";
import { useSimulationSection } from "./useSimulationSection";

export type RealProcessing = { byElement: Map<string, { seconds: number }> | null; logName: string };

/** La lavorazione media per elemento nel log mappato piu' recente del processo, se c'e'. */
export function useRealProcessing(): RealProcessing {
  const { processId } = useSimulationSection();
  const logs = useEventLogs(processId);
  const log = latestMappedLog(logs.data);
  const analysis = useEventLogAnalysis(log?.id ?? null, Boolean(log));
  const summary = analysis.data?.summary ?? null;
  return React.useMemo(
    () => ({ byElement: summary ? realProcessingByElement(summary) : null, logName: log?.name ?? "" }),
    [summary, log?.name],
  );
}

/** SIM-17: i disaccordi fra pannello, file del cliente e log mappato piu' recente. */
export function useSourceConflicts(template: ScenarioTemplate | null, draft: ScenarioDraft, claims: SimulationClaims | null): SourceConflict[] {
  const { t } = useTranslation("process");
  const real = useRealProcessing();
  return React.useMemo(() => sourceConflicts({
    template,
    draft,
    claims,
    realProcessing: real.byElement,
    logName: real.logName,
    panelLabel: t("simulation.sourceConflicts.panel"),
  }), [template, draft, claims, real, t]);
}
