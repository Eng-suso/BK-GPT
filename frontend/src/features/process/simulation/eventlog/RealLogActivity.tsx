import React from "react";
import { useTranslation } from "react-i18next";

import { InlineNotice } from "@/components/feedback";
import { httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";

import { formatDuration, MISSING_VALUE } from "../simulationResults";
import type { SimulationRun, SimulationSummary } from "../simulationTypes";
import { useSimulationSection } from "../useSimulationSection";
import { compareRealToSimulated, latestMappedLog, signedPercent } from "./realVsSimulated";
import { useEventLogAnalysis, useEventLogs } from "./useEventLogImport";
import "./eventLog.css";

/**
 * B2 nell'inspector del task: la stessa attivita' nel log reale piu' recente e
 * nel run, con lo scarto della lavorazione. Senza log mappato invita a importarlo.
 */
export function RealLogActivity({ run, elementId }: { run: SimulationRun; elementId: string }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const { processId, openPanel } = useSimulationSection();
  const logs = useEventLogs(processId);
  const log = latestMappedLog(logs.data);
  const analysis = useEventLogAnalysis(log?.id ?? null, Boolean(log));
  const title = t("simulation.eventLog.inspector.title");

  if (logs.isPending || (log && analysis.isPending)) {
    return <section className="sim-real-activity" aria-label={title} aria-busy="true"><h4>{title}</h4><Skeleton className="h-10 w-full" /></section>;
  }
  const error = logs.error ?? analysis.error;
  if (error) {
    return (
      <section className="sim-real-activity" aria-label={title}>
        <InlineNotice tone="error" title={t("simulation.eventLog.inspector.failed")}
          action={<Button size="sm" variant="outline" onClick={() => void (logs.isError ? logs.refetch() : analysis.refetch())}>{t("simulation.eventLog.retry")}</Button>}>
          {httpErrorMessage(error, t("simulation.eventLog.inspector.failed"))}
        </InlineNotice>
      </section>
    );
  }
  if (!log) {
    return (
      <section className="sim-real-activity" aria-label={title}>
        <h4>{title}</h4>
        <p className="sim-help">{t("simulation.eventLog.inspector.noLog")}</p>
        {openPanel && <Button size="sm" variant="ghost" onClick={() => openPanel("eventLog")}>{t("simulation.eventLog.inspector.import")}</Button>}
      </section>
    );
  }
  const summary = analysis.data?.summary;
  const row = summary && run.summary
    ? compareRealToSimulated(summary, run.summary as SimulationSummary).activities.find((item) => item.el === elementId)
    : undefined;
  return (
    <section className="sim-real-activity" aria-label={title}>
      <h4>{title}<small>{log.name}</small></h4>
      {!row ? (
        <p className="sim-help">{t("simulation.eventLog.inspector.notInLog")}</p>
      ) : (
        <dl>
          <div>
            <dt>{t("simulation.eventLog.inspector.processing")}</dt>
            <dd>
              {formatDuration(row.realProcessing, lang)} → {formatDuration(row.simulatedProcessing, lang)}
              {row.fidelity && <span className="sim-gap" data-fidelity={row.fidelity}>{signedPercent(row.processingGap, lang)}</span>}
            </dd>
          </div>
          <div>
            <dt>{t("simulation.eventLog.inspector.waiting")}</dt>
            <dd>{row.realWait === null ? MISSING_VALUE : formatDuration(row.realWait, lang)} → {row.simulatedWait === null ? MISSING_VALUE : formatDuration(row.simulatedWait, lang)}</dd>
          </div>
          <div>
            <dt>{t("simulation.eventLog.inspector.executions")}</dt>
            <dd>{row.realCount} → {row.simulatedCount}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
