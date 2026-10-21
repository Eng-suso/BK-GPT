import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";

import { Meter } from "@/components/data";
import { Button } from "@/ui/button";

import { queueHotspots } from "./perspective";
import { formatDuration, formatPercent, type SimulationInsights } from "./simulationResults";
import { useSimulationSection } from "./useSimulationSection";

/**
 * SIM-21, vista Operations: dove si accumula il lavoro e il passo successivo.
 * Solo risultati misurati dal run, nessun parametro del modello.
 */
export function OperationsBrief({ insights }: { insights: SimulationInsights }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { selectedElementId, selectElement, openPanel } = useSimulationSection();
  if (!insights.hasData) return null;
  const rows = queueHotspots(insights);
  return (
    <section aria-labelledby="sim-ops-queues" className="ui-surface ui-surface-panel p-4" data-sim-operations-brief>
      <h2 id="sim-ops-queues" className="text-sm font-semibold text-foreground">{t("simulation.perspective.ops.queuesTitle")}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{t("simulation.perspective.ops.queuesHint")}</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">{t("simulation.perspective.ops.noQueues")}</p>
      ) : (
        <ol className="mt-3 grid gap-2">
          {rows.map(({ task, share }) => {
            const selected = task.elementId != null && task.elementId === selectedElementId;
            return (
              <li key={task.elementId ?? task.name} className="grid gap-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  {task.elementId && selectElement ? (
                    <button type="button" className="min-w-0 truncate text-left font-medium text-foreground underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring" aria-pressed={selected} onClick={() => selectElement(selected ? null : task.elementId)}>
                      {task.name}
                    </button>
                  ) : <span className="min-w-0 truncate font-medium text-foreground">{task.name}</span>}
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {t("simulation.perspective.ops.queueRow", { wait: formatDuration(task.avgWaitingSec, lang), share: formatPercent(share) })}
                  </span>
                </div>
                <Meter value={Math.round(share * 100)} label={t("simulation.perspective.ops.queueShare", { name: task.name })} tone={share >= 0.5 ? "danger" : share >= 0.25 ? "warning" : "ok"} showValue={false} height={4} />
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
