import React from "react";
import { useTranslation } from "react-i18next";

import { StatTile } from "@/components/data";

import type { ReplayEngine } from "../replay/replayEngine";
import { useReplayFrame } from "../replay/useReplay";
import { formatCurrency, formatDuration } from "../simulationResults";

type KpiTickerProps = { engine: ReplayEngine };

/** Live "as of the playhead" KPI row, bound to the AnalyticsClock frame. */
export function KpiTicker({ engine }: KpiTickerProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const g = frame?.global;

  const num = React.useMemo(
    () => new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US"),
    [lang],
  );

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
      <StatTile
        label={t("simulation.replay.active")}
        value={num.format(g?.activeCases ?? 0)}
      />
      <StatTile
        label={t("simulation.replay.queued")}
        value={num.format(g?.queuedCases ?? 0)}
        tone={(g?.queuedCases ?? 0) > 0 ? "warning" : "neutral"}
      />
      <StatTile
        label={t("simulation.replay.completed")}
        value={num.format(g?.completedCases ?? 0)}
      />
      <StatTile
        label={t("simulation.dashboard.throughput")}
        value={`${num.format(Math.round(g?.throughputPerHour ?? 0))}/h`}
      />
      <StatTile
        label={t("simulation.dashboard.avgCycle")}
        value={formatDuration(g?.avgCycleSec ?? 0, lang)}
      />
      <StatTile
        label={t("simulation.dashboard.costAccrued")}
        value={formatCurrency(g?.costAccrued ?? 0, lang)}
      />
    </div>
  );
}
