import React from "react";
import { useTranslation } from "react-i18next";

import { TransportBar } from "../replay/TransportBar";
import { ReplayGate } from "../replay/ReplayGate";
import { useReplayFrame } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import { KpiTicker } from "../charts/KpiTicker";
import { TimeSeriesChart, type TimeSeriesPoint } from "../charts/TimeSeriesChart";
import { AsOfBarList, type AsOfRow } from "../charts/AsOfBarList";
import { SIM_SERIES } from "../charts/chartTheme";
import {
  formatCurrency,
  formatCurrencyShort,
  formatDuration,
  formatDurationShort,
} from "../simulationResults";

export function SimulationDashboardPage(): React.JSX.Element {
  return (
    <ReplayGate>{({ engine }) => <DashboardBody engine={engine} />}</ReplayGate>
  );
}

function DashboardBody({ engine }: { engine: ReplayEngine }): React.JSX.Element {
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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TransportBar engine={engine} />
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto grid max-w-[1100px] gap-3">
          <KpiTicker engine={engine} />

          <div className="grid gap-3 lg:grid-cols-2">
            <TimeSeriesChart
              title={t("simulation.dashboard.throughputChart")}
              engine={engine}
              data={data}
              series={[
                { key: "throughput", label: t("simulation.dashboard.throughput"), color: SIM_SERIES.throughput },
              ]}
              formatTime={formatTime}
            />
            <TimeSeriesChart
              title={t("simulation.dashboard.loadChart")}
              engine={engine}
              data={data}
              series={[
                { key: "wip", label: t("simulation.replay.active"), color: SIM_SERIES.wip },
                { key: "queued", label: t("simulation.replay.queued"), color: SIM_SERIES.queue },
              ]}
              formatTime={formatTime}
            />
            <TimeSeriesChart
              title={t("simulation.dashboard.costChart")}
              engine={engine}
              data={data}
              series={[
                { key: "cost", label: t("simulation.dashboard.costAccrued"), color: SIM_SERIES.cost },
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
                { key: "cycle", label: t("simulation.dashboard.avgCycle"), color: SIM_SERIES.cycle },
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
      </div>
    </div>
  );
}
