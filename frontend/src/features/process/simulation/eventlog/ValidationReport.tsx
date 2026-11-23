import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { InlineNotice } from "@/components/feedback";
import { httpErrorMessage, http } from "@/lib/http";

import { formatDuration } from "../simulationResults";
import { groupMembers } from "../replications";
import type { SimulationRun } from "../simulationTypes";

type Estimate = { mean: number; ci95Half: number | null; min: number; max: number };
type Kpi = Estimate & { real: number; bias: number; mae: number };
type Report = {
  referenceCases: number;
  simulatedCases: number[];
  replications: number;
  runIds: number[];
  kpis: Record<"cycle" | "p50" | "p90" | "between" | "processing" | "throughput", Kpi>;
  distances: { cycleW1: Estimate; ngd: Estimate };
  pooledCycle: { p50: number; p90: number };
  firstWaitSimulated: Estimate | null;
  quality: { rowsExcluded: number; eventsWithoutStart: number };
  provenance: { eventLogId: string; runs: { runId: number; seed: number | null; engine: string | null; engineVersion: string | null; startDate: string | null; warmupCases: number }[] };
  basis: string;
};

export function ValidationReport({ eventLogId, run, runs, completeOnly = false }: {
  eventLogId: string;
  run: SimulationRun;
  runs: SimulationRun[];
  /** Il log registra solo i completamenti: il server non confronta i tempi, lo si spiega. */
  completeOnly?: boolean;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const members = groupMembers(run, runs);
  const selected = (members.length > 0 ? members : [run]).filter((item) => item.status === "completed" && item.summary);
  const ids = selected.map((item) => item.id).sort((a, b) => a - b);
  const key = ids.join(",");
  const report = useQuery({
    queryKey: ["event-log-validation", eventLogId, key],
    queryFn: async () => http<Report>(`/v1/workspace/event-logs/${encodeURIComponent(eventLogId)}/validation?${ids.map((id) => `run_ids=${id}`).join("&")}`),
    enabled: ids.length > 0 && !completeOnly,
  });
  const number = (value: number) => value.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 });
  const duration = (seconds: number) => formatDuration(seconds, lang);
  const rows = ["cycle", "p50", "p90", "between", "processing", "throughput"] as const;
  const display = (key: typeof rows[number], value: number) => key === "throughput" ? `${number(value)}/h` : duration(value);
  const missingStart = report.data?.provenance.runs.some((item) => !item.startDate) ?? false;

  return (
    <section className="rounded-md border border-border p-3" aria-label={t("simulation.eventLog.compare.validation.title")}>
      <h3 className="sim-eventlog-title">{t("simulation.eventLog.compare.validation.title")}</h3>
      {completeOnly && <InlineNotice title={t("simulation.eventLog.compare.validation.completeOnlyTitle")}>
        {t("simulation.eventLog.compare.validation.completeOnly")}
      </InlineNotice>}
      {report.isPending && !completeOnly && <p role="status">{t("simulation.eventLog.compare.validation.loading")}</p>}
      {report.isError && <InlineNotice tone="error" title={t("simulation.eventLog.compare.validation.error")}>
        {httpErrorMessage(report.error, t("simulation.eventLog.compare.validation.error"))}
      </InlineNotice>}
      {report.data && <>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.scope", { runs: report.data.replications, cases: report.data.referenceCases })}</p>
        {missingStart && <InlineNotice tone="error" title={t("simulation.eventLog.compare.validation.unanchoredTitle")}>
          {t("simulation.eventLog.compare.validation.unanchored")}
        </InlineNotice>}
        {!missingStart && <>
        {report.data.simulatedCases.some((count) => count !== report.data.referenceCases) &&
          <InlineNotice tone="warning" title={t("simulation.eventLog.compare.validation.caseCountTitle")}>
            {t("simulation.eventLog.compare.validation.caseCount")}
          </InlineNotice>}
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.basis")}</p>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.calibration")}</p>
        <div className="overflow-x-auto">
          <table className="sim-gap-table">
            <thead><tr>
              <th scope="col">{t("simulation.eventLog.compare.kpi")}</th>
              <th scope="col">{t("simulation.eventLog.compare.real")}</th>
              <th scope="col">{t("simulation.eventLog.compare.validation.replicaMean")}</th>
              <th scope="col">{t("simulation.eventLog.compare.validation.bias")}</th>
              <th scope="col">{t("simulation.eventLog.compare.validation.mae")}</th>
            </tr></thead>
            <tbody>{rows.map((key) => {
              const value = report.data.kpis[key];
              return <tr key={key}>
                <th scope="row">{t(`simulation.eventLog.compare.validation.metric.${key}`)}</th>
                <td>{display(key, value.real)}</td>
                <td>{display(key, value.mean)}{value.ci95Half !== null && <small>± {display(key, value.ci95Half)} (95%)</small>}</td>
                <td>{value.bias > 0 ? "+" : value.bias < 0 ? "−" : ""}{display(key, Math.abs(value.bias))}</td>
                <td>{display(key, value.mae)}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.uncertainty")}</p>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.pooled", {
          p50: duration(report.data.pooledCycle.p50), p90: duration(report.data.pooledCycle.p90),
        })}</p>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.distances", {
          cycle: duration(report.data.distances.cycleW1.mean),
          cycleCi: report.data.distances.cycleW1.ci95Half === null ? "—" : duration(report.data.distances.cycleW1.ci95Half),
          ngd: number(report.data.distances.ngd.mean * 100),
          ngdCi: report.data.distances.ngd.ci95Half === null ? "—" : number(report.data.distances.ngd.ci95Half * 100),
        })}</p>
        </>}
        {!missingStart && report.data.firstWaitSimulated && <InlineNotice tone="warning" title={t("simulation.eventLog.compare.validation.firstWaitTitle")}>
          {t("simulation.eventLog.compare.validation.firstWait", { value: duration(report.data.firstWaitSimulated.mean) })}
        </InlineNotice>}
        {(report.data.quality.rowsExcluded > 0 || report.data.quality.eventsWithoutStart > 0) &&
          <InlineNotice tone="warning" title={t("simulation.eventLog.compare.validation.qualityTitle")}>
            {t("simulation.eventLog.compare.validation.quality", report.data.quality)}
          </InlineNotice>}
        <details>
          <summary>{t("simulation.eventLog.compare.validation.provenance")}</summary>
          <ul className="list-disc pl-5 text-sm text-muted-foreground">
            {report.data.provenance.runs.map((item) => <li key={item.runId}>
              #{item.runId} · {item.engine ?? "—"} {item.engineVersion ?? ""} · seed {item.seed ?? "—"} · {item.startDate ?? t("simulation.eventLog.compare.validation.startMissing")} · warm-up {item.warmupCases}
            </li>)}
          </ul>
        </details>
      </>}
    </section>
  );
}
