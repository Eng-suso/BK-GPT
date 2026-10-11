import React from "react";
import { useTranslation } from "react-i18next";

import { formatCurrency, formatDuration } from "./simulationResults";
import { groupMembers, replicationIntervals, type Interval, type ReplicationKpi } from "./replications";
import type { SimulationRun } from "./simulationTypes";
import { useSimulationSection } from "./useSimulationSection";

/**
 * SIM-04: i KPI del gruppo di ripetizioni, ognuno con il suo intervallo al 95%.
 * Niente se il run non fa parte di un gruppo.
 */
export function ReplicationSummary({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { runs } = useSimulationSection();
  return <ReplicationTable run={run} runs={runs ?? []} />;
}

export function ReplicationTable({ run, runs }: { run: SimulationRun; runs: SimulationRun[] }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const members = groupMembers(run, runs);
  if (members.length === 0) return null;
  const completed = members.filter((r) => r.status === "completed").length;
  const failed = members.filter((r) => r.status === "failed").length;
  const intervals = replicationIntervals(members);
  const formats: Record<ReplicationKpi, (value: number) => string> = {
    cycle: (v) => formatDuration(v, lang),
    waiting: (v) => formatDuration(v, lang),
    costPerCase: (v) => formatCurrency(v, lang),
    throughput: (v) => t("simulation.results.replicationPerHour", { value: v.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 }) }),
  };
  const row = (kpi: ReplicationKpi, value: Interval | null) => value && (
    <tr key={kpi}>
      <th scope="row" className="py-1 pr-3 text-left font-normal text-muted-foreground">{t(`simulation.results.replicationKpi.${kpi}`)}</th>
      <td className="py-1 text-right text-foreground">{t("simulation.results.replicationValue", { mean: formats[kpi](value.mean), half: formats[kpi](value.half) })}</td>
    </tr>
  );
  return (
    <section aria-label={t("simulation.results.replications")} className="mb-3 grid gap-1 rounded-md border border-border p-3" data-sim-replications>
      <p className="text-sm font-medium text-foreground">{t("simulation.results.replications")}</p>
      <p className="text-xs text-muted-foreground" role="status">
        {t("simulation.results.replicationProgress", { done: completed, total: members.length })}
        {failed > 0 && ` ${t("simulation.results.replicationFailed", { count: failed })}`}
      </p>
      {completed >= 2 ? (
        <>
          <table className="w-full text-sm">
            <tbody>{(Object.keys(intervals) as ReplicationKpi[]).map((kpi) => row(kpi, intervals[kpi]))}</tbody>
          </table>
          <p className="text-xs text-muted-foreground">{t("simulation.results.replicationHint", { count: completed })}</p>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{t("simulation.results.replicationWaiting")}</p>
      )}
    </section>
  );
}
