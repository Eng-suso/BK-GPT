import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Map as MapIcon } from "lucide-react";

import { EmptyState, InlineNotice } from "@/components/feedback";
import { Button } from "@/ui/button";
import { http, httpErrorMessage } from "@/lib/http";

import type { NodeDecoration } from "../canvas/SimulationCanvas";
import { formatCount, formatCurrency, formatDuration, MISSING_VALUE } from "../simulationResults";
import type { SimulationSummary } from "../simulationTypes";
import { formatRunOption, useSimulationSection } from "../useSimulationSection";
import type { EventLogSummary } from "./eventLogTypes";
import { compareRealToSimulated, signedPercent, withComparableKpis, type ActivityGap, type ComparableKpis, type Fidelity, type GapFormat, type KpiGap } from "./realVsSimulated";
import { ValidationReport } from "./ValidationReport";

const BADGE_TONE: Record<Fidelity, NodeDecoration["badgeTone"]> = { close: "neutral", calibrate: "warning", far: "danger" };

/** Il log reale accanto a un run simulato: processo, attivita' e scarti sul disegno. */
export function RealVsSimulatedStep({ eventLogId, summary, realCases, onDecorations }: {
  eventLogId?: string;
  summary: EventLogSummary;
  realCases: number;
  onDecorations?: (items: NodeDecoration[] | null) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { runs, activeRunId, openPanel } = useSimulationSection();
  const completed = React.useMemo(() => runs.filter((run) => run.status === "completed" && run.summary), [runs]);
  const [runId, setRunId] = React.useState<number | null>(() => completed.find((run) => run.id === activeRunId)?.id ?? completed[0]?.id ?? null);
  const run = completed.find((item) => item.id === runId) ?? completed[0] ?? null;
  const [onCanvas, setOnCanvas] = React.useState(false);
  const comparison = React.useMemo(
    () => (run?.summary ? compareRealToSimulated(summary, run.summary as SimulationSummary) : null),
    [summary, run],
  );
  const selectedValidation = useQuery({
    queryKey: ["event-log-validation", eventLogId, String(run?.id ?? "")],
    queryFn: () => http<{ kpis: ComparableKpis; initialActivities: string[] }>(`/v1/workspace/event-logs/${encodeURIComponent(eventLogId!)}/validation?run_ids=${run!.id}`),
    enabled: Boolean(eventLogId && run && run.request?.start_date !== null),
  });

  const decorations = React.useMemo<NodeDecoration[]>(
    () => (comparison?.activities ?? []).flatMap((row) => row.fidelity
      ? [{ elementId: row.el, markers: [`sim-fidelity-${row.fidelity}`], badge: signedPercent(row.processingGap, lang), badgeTone: BADGE_TONE[row.fidelity] }]
      : []),
    [comparison, lang],
  );
  React.useEffect(() => { onDecorations?.(onCanvas ? decorations : null); }, [onCanvas, decorations, onDecorations]);
  React.useEffect(() => () => onDecorations?.(null), [onDecorations]);

  if (!run || !comparison) {
    return (
      <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.compare")}>
        <EmptyState
          title={t("simulation.eventLog.compare.noRun")}
          description={t("simulation.eventLog.compare.noRunHint")}
          action={openPanel ? <Button size="sm" onClick={() => openPanel("scenario")}>{t("simulation.unified.tool.scenario")}</Button> : undefined}
        />
      </section>
    );
  }

  if (run.request?.start_date === null) {
    return (
      <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.compare")}>
        <label className="sim-field">
          <span>{t("simulation.eventLog.compare.run")}</span>
          <select value={run.id} onChange={(event) => setRunId(Number(event.target.value))}>
            {completed.map((item) => <option key={item.id} value={item.id}>{formatRunOption(item, lang)}</option>)}
          </select>
        </label>
        <InlineNotice tone="error" title={t("simulation.eventLog.compare.validation.unanchoredTitle")}>
          {t("simulation.eventLog.compare.validation.unanchored")}
        </InlineNotice>
        {openPanel && <Button size="sm" onClick={() => openPanel("scenario")}>{t("simulation.unified.tool.scenario")}</Button>}
      </section>
    );
  }

  const comparable = selectedValidation.data
    ? withComparableKpis(comparison, selectedValidation.data.kpis, selectedValidation.data.initialActivities)
    : eventLogId ? null : comparison;
  const cycle = comparable?.process.find((row) => row.key === "cycleAvg");
  const p90 = comparable?.process.find((row) => row.key === "cycleP90");
  return (
    <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.compare")}>
      {eventLogId && <ValidationReport eventLogId={eventLogId} run={run} runs={runs} />}
      <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.intro")}</p>
      <label className="sim-field">
        <span>{t("simulation.eventLog.compare.run")}</span>
        <select value={run.id} onChange={(event) => setRunId(Number(event.target.value))}>
          {completed.map((item) => <option key={item.id} value={item.id}>{formatRunOption(item, lang)}</option>)}
        </select>
      </label>

      {comparable?.fidelity && (
        <div className="sim-fidelity-verdict" data-fidelity={comparable.fidelity} role="status">
          <strong>{t(`simulation.eventLog.compare.verdict.${comparable.fidelity}`)}</strong>
          <span>{t("simulation.eventLog.compare.verdictDetail", { cycle: signedPercent(cycle?.gap ?? null, lang), p90: signedPercent(p90?.gap ?? null, lang) })}</span>
        </div>
      )}
      <p className="sim-eventlog-hint">
        {t("simulation.eventLog.compare.cases", { real: formatCount(realCases, lang), simulated: formatCount(run.summary?.casesCompleted ?? 0, lang) })}
      </p>

      <h3 className="sim-eventlog-title">{t("simulation.eventLog.compare.process")}</h3>
      {selectedValidation.isPending && eventLogId && <p role="status">{t("simulation.eventLog.compare.validation.loading")}</p>}
      {selectedValidation.isError && <InlineNotice tone="error" title={t("simulation.eventLog.compare.validation.error")}>
        {httpErrorMessage(selectedValidation.error, t("simulation.eventLog.compare.validation.error"))}
      </InlineNotice>}
      {comparable &&
      <table className="sim-gap-table">
        <thead>
          <tr>
            <th scope="col">{t("simulation.eventLog.compare.kpi")}</th>
            <th scope="col">{t("simulation.eventLog.compare.real")}</th>
            <th scope="col">{t("simulation.eventLog.compare.simulated")}</th>
            <th scope="col">{t("simulation.eventLog.compare.gap")}</th>
          </tr>
        </thead>
        <tbody>
          {comparable.process.map((row) => (
            <tr key={row.key}>
              <th scope="row">{t(`simulation.eventLog.compare.kpiName.${row.key}`)}</th>
              <td>{formatValue(row.real, row.format, lang, t)}</td>
              <td>{formatValue(row.simulated, row.format, lang, t)}</td>
              <td><GapCell row={row} lang={lang} /></td>
            </tr>
          ))}
        </tbody>
      </table>}
      {comparable && summary.firstEnableObserved !== true && run.summary?.cycle?.avg != null &&
        <p className="sim-eventlog-hint">{t("simulation.eventLog.compare.validation.fullCycleOnlySimulated", {
          value: formatDuration(run.summary.cycle.avg, lang),
        })}</p>}

      <div className="sim-eventlog-head sim-gap-head">
        <h3 className="sim-eventlog-title">{t("simulation.eventLog.compare.activities")}</h3>
        {decorations.length > 0 && (
          <Button size="sm" variant={onCanvas ? "secondary" : "outline"} aria-pressed={onCanvas} onClick={() => setOnCanvas((value) => !value)}>
            <MapIcon aria-hidden className="size-4" />
            {t("simulation.eventLog.compare.showOnProcess")}
          </Button>
        )}
      </div>
      {comparable && comparable.activities.length === 0 ? (
        <InlineNotice tone="warning" title={t("simulation.eventLog.compare.noActivities")} />
      ) : comparable ? (
        <table className="sim-gap-table">
          <caption className="sr-only">{t("simulation.eventLog.compare.activitiesCaption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("simulation.eventLog.compare.activity")}</th>
              <th scope="col">{t("simulation.eventLog.compare.real")}</th>
              <th scope="col">{t("simulation.eventLog.compare.simulated")}</th>
              <th scope="col">{t("simulation.eventLog.compare.gap")}</th>
            </tr>
          </thead>
          <tbody>
            {comparable.activities.map((row) => <ActivityRow key={row.el} row={row} lang={lang} />)}
          </tbody>
        </table>
      ) : null}
      {comparison.unmatchedReal.length > 0 && (
        <InlineNotice title={t("simulation.eventLog.compare.unmatched", { count: comparison.unmatchedReal.length })}>
          {comparison.unmatchedReal.join(", ")}
        </InlineNotice>
      )}
      {comparison.notSimulated.length > 0 && (
        <InlineNotice tone="warning" title={t("simulation.eventLog.compare.notSimulated", { count: comparison.notSimulated.length })}>
          {comparison.notSimulated.join(", ")}
        </InlineNotice>
      )}
      {comparison.unobservedSimulated.length > 0 && (
        <InlineNotice tone="warning" title={t("simulation.eventLog.compare.unobserved", { count: comparison.unobservedSimulated.length })}>
          {comparison.unobservedSimulated.join(", ")}
        </InlineNotice>
      )}
    </section>
  );
}

function ActivityRow({ row, lang }: { row: ActivityGap; lang: "it" | "en" }): React.JSX.Element {
  const { t } = useTranslation("process");
  const wait = (value: number | null) => value === null ? null : <small>{t("simulation.eventLog.compare.waitShort", { value: formatDuration(value, lang) })}</small>;
  return (
    <tr>
      <th scope="row">{row.name}{row.logNames.length > 1 && <small>{t("simulation.eventLog.compare.merged", { names: row.logNames.join(", ") })}</small>}</th>
      <td>{row.realProcessing === null ? <span className="sim-gap-missing">{MISSING_VALUE}<small>{t("simulation.eventLog.compare.notComparable.noStart")}</small></span> : formatDuration(row.realProcessing, lang)}{row.initialWaitUnobserved ? <small>{t("simulation.eventLog.compare.validation.initialWaitUnknown")}</small> : wait(row.realWait)}</td>
      <td>{formatDuration(row.simulatedProcessing, lang)}{wait(row.simulatedWait)}</td>
      <td>
        {row.fidelity
          ? <span className="sim-gap" data-fidelity={row.fidelity}>{signedPercent(row.processingGap, lang)}</span>
          : <span className="sim-gap-missing">{MISSING_VALUE}</span>}
      </td>
    </tr>
  );
}

function GapCell({ row, lang }: { row: KpiGap; lang: "it" | "en" }): React.JSX.Element {
  const { t } = useTranslation("process");
  if (row.notComparable) {
    return <span className="sim-gap-missing">{MISSING_VALUE}<small>{t(`simulation.eventLog.compare.notComparable.${row.notComparable}`)}</small></span>;
  }
  return <span className="sim-gap" data-fidelity={row.fidelity ?? undefined}>{signedPercent(row.gap, lang)}</span>;
}

function formatValue(value: number | null, format: GapFormat, lang: "it" | "en", t: ReturnType<typeof useTranslation>["t"]): string {
  if (value === null) return MISSING_VALUE;
  if (format === "duration") return formatDuration(value, lang);
  if (format === "currency") return formatCurrency(value, lang);
  return t("simulation.eventLog.compare.perHour", { value: value.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 }) });
}
