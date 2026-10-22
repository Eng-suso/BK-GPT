import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";

import { Meter } from "@/components/data";
import { Button } from "@/ui/button";

import { queueHotspots } from "./perspective";
import { formatDuration, formatPercent } from "./simulationResults";
import type { SimulationSummary } from "./simulationTypes";
import { useSimulationSection } from "./useSimulationSection";

/**
 * SIM-21, vista Operations: dove si accumula il lavoro e il passo successivo.
 * Solo risultati misurati dal run, nessun parametro del modello.
 */
export function OperationsBrief({ summary }: { summary: SimulationSummary | null | undefined }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { selectedElementId, selectElement, openPanel } = useSimulationSection();
  if (!summary) return null;
  const rows = queueHotspots(summary.byActivity);
  return (
    <section aria-labelledby="sim-ops-queues" className="ui-surface ui-surface-panel p-4" data-sim-operations-brief>
      <h2 id="sim-ops-queues" className="text-sm font-semibold text-foreground">{t("simulation.perspective.ops.queuesTitle")}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{t("simulation.perspective.ops.queuesHint")}</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">{t("simulation.perspective.ops.noQueues")}</p>
      ) : (
        <ol className="mt-3 grid gap-2">
          {rows.map((row) => {
            const selected = row.el != null && row.el === selectedElementId;
            return (
              <li key={row.el ?? row.name} className="grid gap-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  {row.el && selectElement ? (
                    <button type="button" className="min-w-0 truncate text-left font-medium text-foreground underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring" aria-pressed={selected} onClick={() => selectElement(selected ? null : row.el)}>
                      {row.name}
                    </button>
                  ) : <span className="min-w-0 truncate font-medium text-foreground">{row.name}</span>}
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {t("simulation.perspective.ops.queueRow", { wait: formatDuration(row.avgWaitSec, lang), share: formatPercent(row.share) })}
                  </span>
                </div>
                <Meter value={Math.round(row.share * 100)} label={t("simulation.perspective.ops.queueShare", { name: row.name })} tone={row.share >= 0.5 ? "danger" : row.share >= 0.25 ? "warning" : "ok"} showValue={false} height={4} />
                {row.queueAvg != null && <span className="text-2xs text-muted-foreground">{t("simulation.perspective.ops.queueLength", { count: Number(row.queueAvg.toFixed(1)), value: new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 1 }).format(row.queueAvg) })}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {openPanel && (
        <Button type="button" size="sm" variant="outline" className="mt-3 gap-1.5" onClick={() => openPanel("insights")}>
          {t("simulation.perspective.ops.whatToTry")}
          <ArrowRight aria-hidden className="size-3.5" />
        </Button>
      )}
    </section>
  );
}
