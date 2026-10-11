import React from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { formatCurrency, formatDuration } from "./simulationResults";
import { compareGroups, type DeltaInterval, type ReplicationKpi } from "./replications";
import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-04, seconda parte: nel confronto, la differenza fra i due scenari ripetuti
 * con il suo intervallo al 95%. Se uno dei due non e' ripetuto, dice come
 * ottenere un confronto difendibile.
 */
export function ReplicationDelta({ runA, runB, runs }: { runA: SimulationRun; runB: SimulationRun; runs: SimulationRun[] }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const comparison = compareGroups(runA, runB, runs);
  if (!comparison) {
    return <p className="text-xs text-muted-foreground" data-sim-replication-delta-hint>{t("simulation.compare.repeatBoth")}</p>;
  }
  const number = (v: number) => v.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 });
  const formats: Record<ReplicationKpi, (value: number) => string> = {
    cycle: (v) => formatDuration(v, lang),
    waiting: (v) => formatDuration(v, lang),
    costPerCase: (v) => formatCurrency(v, lang),
    throughput: (v) => t("simulation.results.replicationPerHour", { value: number(v) }),
  };
  const signed = (kpi: ReplicationKpi, v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${formats[kpi](Math.abs(v))}`;
  const row = (kpi: ReplicationKpi, value: DeltaInterval | null) => value && (
    <tr key={kpi} className="border-t border-border">
      <th scope="row" className="py-1.5 pr-3 text-left font-normal text-muted-foreground">{t(`simulation.results.replicationKpi.${kpi}`)}</th>
      <td className="py-1.5 pr-3 text-right tabular-nums text-foreground">
        {t("simulation.results.replicationValue", { mean: signed(kpi, value.delta), half: formats[kpi](value.half) })}
      </td>
      <td className={cn(
        "py-1.5 text-right font-medium",
        value.verdict === "better" && "text-[var(--color-status-success)]",
        value.verdict === "worse" && "text-[var(--color-status-danger)]",
        value.verdict === "unclear" && "text-muted-foreground",
      )}>
        {t(`simulation.compare.deltaVerdict.${value.verdict}`)}
      </td>
    </tr>
  );
  return (
    <section aria-label={t("simulation.compare.replicationDelta")} className="grid gap-1 ui-surface ui-surface-panel px-4 py-2.5" data-sim-replication-delta>
      <p className="text-sm font-medium text-foreground">{t("simulation.compare.replicationDelta")}</p>
      <p className="text-xs text-muted-foreground">
        {t(comparison.paired ? "simulation.compare.pairedGroups" : "simulation.compare.independentGroups", { a: comparison.nA, b: comparison.nB })}
      </p>
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th scope="col" className="py-1 text-left font-normal text-muted-foreground">{t("simulation.compare.metric")}</th>
            <th scope="col" className="py-1 pr-3 text-right font-normal text-muted-foreground">{t("simulation.compare.deltaHeader")}</th>
            <th scope="col" className="py-1 text-right font-normal text-muted-foreground">{t("simulation.compare.outcome")}</th>
          </tr>
        </thead>
        <tbody>{(Object.keys(comparison.kpis) as ReplicationKpi[]).map((kpi) => row(kpi, comparison.kpis[kpi]))}</tbody>
      </table>
      <p className="text-xs text-muted-foreground">{t("simulation.compare.deltaHint")}</p>
    </section>
  );
}
