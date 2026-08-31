import React from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { ReplayEngine } from "./replayEngine";
import { usePlayhead, useReplayStatus } from "./useReplay";
import { formatDuration } from "../simulationResults";

type CaseTimelineProps = {
  engine: ReplayEngine;
};

/**
 * The focused case's own lifeline: one row per activity, a waiting segment
 * (enable → start) then a working segment (start → end), scaled to the case's
 * span so it stays readable. A playhead tracks the replay clock.
 */
export function CaseTimeline({ engine }: CaseTimelineProps): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const status = useReplayStatus(engine);
  const tNow = usePlayhead(engine);

  // Cheap pure reads off the immutable replay artifact — `focusCaseId` in the
  // status is what changes which case these return.
  const focusId = status?.focusCaseId ?? null;
  const rows = engine.focusCaseEvents(focusId);
  const span = engine.focusCaseSpan(focusId);

  if (!rows || !span || rows.length === 0) return null;

  const total = Math.max(1e-6, span.end - span.start);
  const pct = (v: number) => `${(((v - span.start) / total) * 100).toFixed(2)}%`;
  const width = (a: number, b: number) =>
    `${(Math.max(0, b - a) / total) * 100}%`;
  const playFrac = Math.min(1, Math.max(0, (tNow - span.start) / total));

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 pb-2">
        <p className="eyebrow">
          {t("simulation.replay.timeline.title", {
            id: status?.focusCaseId ?? "",
          })}
        </p>
        <span className="text-[11px] text-muted-foreground">
          {t("simulation.replay.timeline.cycle", {
            value: formatDuration(span.cycleSec, lang),
          })}
        </span>
      </div>

      <div className="relative min-h-0 flex-1 overflow-y-auto pr-1">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 z-10 w-px bg-[var(--color-border-strong)]"
          style={{ left: `calc(140px + ${playFrac} * (100% - 140px))` }}
        />
        <ul className="grid gap-1">
          {rows.map((row, i) => (
            <li key={i} className="grid grid-cols-[140px_minmax(0,1fr)] items-center gap-2">
              <span className="truncate text-[11px] text-foreground" title={row.name}>
                {row.name}
              </span>
              <span className="relative h-3.5 rounded-sm bg-muted/50">
                <span
                  className="absolute inset-y-0 rounded-sm bg-[var(--sim-token-queued)]/45"
                  style={{ left: pct(row.enable), width: width(row.enable, row.start) }}
                  title={t("simulation.replay.timeline.wait", {
                    value: formatDuration(row.start - row.enable, lang),
                  })}
                />
                <span
                  className={cn(
                    "absolute inset-y-0 rounded-sm bg-[var(--sim-token)]",
                  )}
                  style={{ left: pct(row.start), width: width(row.start, row.end) }}
                  title={t("simulation.replay.timeline.work", {
                    value: formatDuration(row.end - row.start, lang),
                  })}
                />
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center gap-3 pt-1.5 text-[10px] text-muted-foreground">
        <Legend color="var(--sim-token-queued)" label={t("simulation.replay.timeline.waitLabel")} />
        <Legend color="var(--sim-token)" label={t("simulation.replay.timeline.workLabel")} />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="size-2 rounded-[2px]" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}
