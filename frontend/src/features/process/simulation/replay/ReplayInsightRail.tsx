import React from "react";
import { useTranslation } from "react-i18next";

import {
  DetailPanel,
  DetailPanelKeyValue,
  DetailPanelSection,
} from "@/components/panel";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { Meter } from "@/components/data";

import type { ReplayEngine, ReplayFrame } from "./replayEngine";
import { useReplayFrame, usePlayhead } from "./useReplay";
import type { SimulationRun } from "../simulationTypes";
import { formatDuration } from "../simulationResults";

const PRESSURE_TONE: Record<string, StatusTone> = {
  none: "neutral",
  building: "pending",
  high: "warning",
  saturated: "danger",
};

type ReplayInsightRailProps = {
  engine: ReplayEngine;
  run: SimulationRun;
};

/** The "what am I watching" rail — clock, legend, live bottleneck, resources. */
export function ReplayInsightRail({
  engine,
  run,
}: ReplayInsightRailProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const tNow = usePlayhead(engine);

  const numberFmt = React.useMemo(
    () => new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US"),
    [lang],
  );
  const dateFmt = React.useMemo(
    () =>
      new Intl.DateTimeFormat(lang === "it" ? "it-IT" : "en-US", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
    [lang],
  );

  const dayOf = Math.floor(tNow / 86_400) + 1;
  const daysTotal = Math.max(1, Math.ceil(engine.durationSec / 86_400));
  const clock = frame ? dateFmt.format(new Date(frame.global.clockMs)) : "—";

  const hottest = pickHottest(frame, run);

  return (
    <DetailPanel className="w-[300px] shrink-0 rounded-lg border">
      <div className="pb-4">
        <p className="eyebrow">{t("simulation.replay.rail.clock")}</p>
        <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
          {clock}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("simulation.replay.rail.dayOf", { n: dayOf, total: daysTotal })}
        </p>
      </div>

      <DetailPanelSection title={t("simulation.replay.rail.bottleneck")}>
        {hottest ? (
          <div className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <StatusIndicator
                tone={PRESSURE_TONE[hottest.pressure] ?? "neutral"}
                label={hottest.name}
              />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("simulation.replay.rail.bottleneckLine", {
                queued: numberFmt.format(hottest.queued),
                active: numberFmt.format(hottest.active),
              })}
            </p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {t("simulation.replay.rail.noPressure")}
          </p>
        )}
      </DetailPanelSection>

      {frame && Object.keys(frame.resources).length > 0 && (
        <DetailPanelSection title={t("simulation.replay.rail.resources")}>
          <ul className="grid gap-2">
            {Object.entries(frame.resources).map(([id, res]) => (
              <li key={id} className="grid grid-cols-[minmax(0,1fr)_88px] items-center gap-2">
                <span className="truncate text-xs text-foreground">{id}</span>
                <Meter
                  value={Math.round(res.busy * 100)}
                  tone={res.busy >= 0.95 ? "danger" : res.busy >= 0.8 ? "warning" : "ok"}
                />
              </li>
            ))}
          </ul>
        </DetailPanelSection>
      )}

      <DetailPanelSection title={t("simulation.replay.counters")}>
        <DetailPanelKeyValue
          rows={[
            {
              label: t("simulation.replay.active"),
              value: numberFmt.format(frame?.global.activeCases ?? 0),
            },
            {
              label: t("simulation.replay.queued"),
              value: numberFmt.format(frame?.global.queuedCases ?? 0),
            },
            {
              label: t("simulation.replay.completed"),
              value: numberFmt.format(frame?.global.completedCases ?? 0),
            },
            {
              label: t("simulation.replay.throughput"),
              value: `${numberFmt.format(Math.round(frame?.global.throughputPerHour ?? 0))}/h`,
            },
            {
              label: t("simulation.results.cycleTime"),
              value: formatDuration(frame?.global.avgCycleSec ?? 0, lang),
            },
          ]}
        />
      </DetailPanelSection>

      <DetailPanelSection title={t("simulation.replay.rail.legend")}>
        <ul className="grid gap-1.5 text-xs text-muted-foreground">
          <LegendRow color="var(--sim-token)" label={t("simulation.replay.rail.legendActive")} />
          <LegendRow
            color="var(--sim-token-queued)"
            label={t("simulation.replay.rail.legendQueued")}
          />
        </ul>
      </DetailPanelSection>
    </DetailPanel>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className="size-2.5 rounded-full" style={{ background: color }} aria-hidden />
      {label}
    </li>
  );
}

type Hottest = {
  el: string;
  name: string;
  queued: number;
  active: number;
  pressure: string;
};

/** The node under the most live pressure right now (ties broken by the run's
 *  diagnostic bottleneck). */
function pickHottest(frame: ReplayFrame | null, run: SimulationRun): Hottest | null {
  if (!frame) return null;
  const names = new Map(
    ((run.summary?.byActivity as Array<Record<string, unknown>>) ?? []).map((a) => [
      String(a.el),
      String(a.name ?? a.el),
    ]),
  );
  let best: Hottest | null = null;
  const rank: Record<string, number> = { none: 0, building: 1, high: 2, saturated: 3 };
  for (const [el, s] of Object.entries(frame.elements)) {
    if (s.pressure === "none" && s.queued === 0) continue;
    const cand: Hottest = {
      el,
      name: names.get(el) ?? el,
      queued: s.queued,
      active: s.active,
      pressure: s.pressure,
    };
    if (
      !best ||
      rank[cand.pressure] > rank[best.pressure] ||
      (rank[cand.pressure] === rank[best.pressure] && cand.queued > best.queued)
    ) {
      best = cand;
    }
  }
  return best;
}
