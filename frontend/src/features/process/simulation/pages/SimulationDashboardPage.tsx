import React from "react";
import { useTranslation } from "react-i18next";

import { StatTile } from "@/components/data";

import { TransportBar } from "../replay/TransportBar";
import { ReplayGate } from "../replay/ReplayGate";
import type { ReplayEngine } from "../replay/replayEngine";
import { TimeSeriesChart, type TimeSeriesPoint } from "../charts/TimeSeriesChart";
import { AsOfBarList, type AsOfRow } from "../charts/AsOfBarList";
import { useReplayFrame } from "../replay/useReplay";
import { SIM_SERIES } from "../charts/chartTheme";
import type { SimulationRun, SimulationSummary } from "../simulationTypes";
import {
  formatCurrency,
  formatCurrencyShort,
  formatDuration,
  formatDurationShort,
  formatPercent,
} from "../simulationResults";

export function SimulationDashboardPage(): React.JSX.Element {
  return (
    <ReplayGate>
      {({ engine, run }) => <DashboardBody engine={engine} run={run} />}
    </ReplayGate>
  );
}

function DashboardBody({
  engine,
  run,
}: {
  engine: ReplayEngine;
  run: SimulationRun;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);

  const data: TimeSeriesPoint[] = React.useMemo(() => {
    const s = engine.payload.series;
    return s.t.map((sec, i) => ({
      t: sec,
      throughput: s.global.throughputPerHour?.[i] ?? 0,
      wip: s.global.wip?.[i] ?? 0,
      queued: s.global.queued?.[i] ?? 0,
      cost: s.global.costAccrued?.[i] ?? 0,
      cycle: s.global.avgCycleSec?.[i] ?? 0,
    }));
  }, [engine]);

  const dateFmt = React.useMemo(
    () =>
      new Intl.DateTimeFormat(lang === "it" ? "it-IT" : "en-US", {
        day: "2-digit",
        month: "short",
      }),
    [lang],
  );
  const formatTime = React.useCallback(
    (sec: number) => dateFmt.format(new Date(engine.startMs + sec * 1000)),
    [dateFmt, engine],
  );

  const activityRows: AsOfRow[] = React.useMemo(() => {
    if (!frame) return [];
    return Object.entries(frame.elements).map(([el, state]) => ({
      id: el,
      label: engine.payload.elements[el]?.name ?? el,
      value: state.active,
      secondary: state.queued,
    }));
  }, [frame, engine]);

  const resourceRows: AsOfRow[] = React.useMemo(() => {
    if (!frame) return [];
    return Object.entries(frame.resources).map(([id, r]) => ({
      id,
      label: id,
      value: Math.round(r.busy * 100),
      formatted: `${Math.round(r.busy * 100)}%`,
    }));
  }, [frame]);

  const peakQueue = React.useMemo(
    () => Math.max(0, ...(engine.payload.series.global.queued ?? [])),
    [engine],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pb-4">
      <div className="shrink-0 overflow-hidden rounded-lg border border-border bg-card">
        <TransportBar engine={engine} />
      </div>

      <DashboardHeadline run={run} lang={lang} peakQueue={peakQueue} />

      <div className="grid gap-3 lg:grid-cols-[1.35fr_1fr]">
        <TimeSeriesChart
          title={t("simulation.dashboard.loadChart")}
          caption={t("simulation.dashboard.loadCaption", { peak: peakQueue })}
          engine={engine}
          data={data}
          height={200}
          series={[
            { key: "wip", label: t("simulation.replay.active"), color: SIM_SERIES.wip },
            { key: "queued", label: t("simulation.replay.queued"), color: SIM_SERIES.queue },
          ]}
          formatTime={formatTime}
        />
        <TimeSeriesChart
          title={t("simulation.dashboard.throughputChart")}
          engine={engine}
          data={data}
          height={200}
          series={[
            {
              key: "throughput",
              label: t("simulation.dashboard.throughput"),
              color: SIM_SERIES.throughput,
            },
          ]}
          formatTime={formatTime}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <TimeSeriesChart
          title={t("simulation.dashboard.costChart")}
          engine={engine}
          data={data}
          series={[
            {
              key: "cost",
              label: t("simulation.dashboard.costAccrued"),
              color: SIM_SERIES.cost,
            },
          ]}
          formatValue={(v) => formatCurrency(v, lang)}
          formatAxisValue={(v) => formatCurrencyShort(v, lang)}
          formatTime={formatTime}
        />
        <TimeSeriesChart
          title={t("simulation.dashboard.cycleChart")}
          engine={engine}
          data={data}
          series={[
            {
              key: "cycle",
              label: t("simulation.dashboard.avgCycle"),
              color: SIM_SERIES.cycle,
            },
          ]}
          formatValue={(v) => formatDuration(v, lang)}
          formatAxisValue={(v) => formatDurationShort(v, lang)}
          formatTime={formatTime}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <AsOfBarList
          title={t("simulation.dashboard.perActivity")}
          rows={activityRows}
          color={SIM_SERIES.wip}
          secondaryColor={SIM_SERIES.queue}
          legend={{
            primary: t("simulation.replay.active"),
            secondary: t("simulation.replay.queued"),
          }}
        />
        <AsOfBarList
          title={t("simulation.dashboard.perResource")}
          rows={resourceRows}
          color={SIM_SERIES.cost}
          max={100}
          formatValue={(v) => `${Math.round(v)}%`}
        />
      </div>
    </div>
  );
}

function DashboardHeadline({
  run,
  lang,
  peakQueue,
}: {
  run: SimulationRun;
  lang: "it" | "en";
  peakQueue: number;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const summary = (run.summary as SimulationSummary | null) ?? null;
  const bottleneck =
    (summary?.bottleneck as { name?: string } | null | undefined)?.name ?? null;

  const cycleAvg = Number(summary?.cycle?.avg ?? 0);
  const waitShare = Number(summary?.waiting?.share ?? 0);
  const costPerCase = Number(summary?.cost?.perCase ?? 0);
  const p95 = Number(summary?.cycle?.p95 ?? 0);

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <p className="text-[13px] leading-relaxed text-foreground">
        {bottleneck
          ? t("simulation.dashboard.headline", {
              bottleneck,
              peak: peakQueue,
              share: formatPercent(waitShare),
            })
          : t("simulation.dashboard.headlineNoBottleneck", {
              share: formatPercent(waitShare),
            })}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile
          label={t("simulation.results.cycleTime")}
          value={formatDuration(cycleAvg, lang)}
          hint={t("simulation.compare.kpi.cycleP95") + ` ${formatDuration(p95, lang)}`}
        />
        <StatTile
          label={t("simulation.results.waitingShare", {
            share: formatPercent(waitShare),
          })}
          value={formatPercent(waitShare)}
        />
        <StatTile
          label={t("simulation.results.costPerCase")}
          value={formatCurrency(costPerCase, lang)}
        />
        <StatTile
          label={t("simulation.dashboard.peakQueue")}
          value={String(peakQueue)}
        />
      </div>
    </section>
  );
}
