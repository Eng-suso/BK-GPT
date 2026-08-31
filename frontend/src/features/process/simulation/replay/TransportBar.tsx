import React from "react";
import { useTranslation } from "react-i18next";
import { Pause, Play, RotateCcw } from "lucide-react";

import { Button } from "@/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

import { type Granularity, type ReplayEngine } from "./replayEngine";
import { useReplayFrame, useReplayStatus, usePlayhead } from "./useReplay";

const GRANULARITIES: Granularity[] = ["case", "sample", "system"];

type TransportBarProps = {
  engine: ReplayEngine;
};

export function TransportBar({ engine }: TransportBarProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it-IT" : "en-US";
  const status = useReplayStatus(engine);
  const frame = useReplayFrame(engine);
  const tNow = usePlayhead(engine);

  const numberFmt = React.useMemo(() => new Intl.NumberFormat(lang), [lang]);
  const clockFmt = React.useMemo(
    () =>
      new Intl.DateTimeFormat(lang, {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
    [lang],
  );

  if (!status) return <div className="h-[52px] border-b border-border" />;

  const duration = status.durationSec;
  const clock = frame ? clockFmt.format(new Date(frame.global.clockMs)) : "—";

  return (
    <div className="flex flex-col gap-2 border-b border-border bg-card px-3 py-2">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-[92px] shrink-0"
          onClick={() => engine.toggle()}
        >
          {status.playing ? (
            <>
              <Pause aria-hidden className="size-3.5" />
              {t("simulation.replay.pause")}
            </>
          ) : (
            <>
              <Play aria-hidden className="size-3.5" />
              {status.atEnd
                ? t("simulation.replay.replay")
                : t("simulation.replay.play")}
            </>
          )}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="size-8 shrink-0 p-0 text-muted-foreground"
          onClick={() => engine.restart()}
          aria-label={t("simulation.replay.restart")}
        >
          <RotateCcw aria-hidden className="size-3.5" />
        </Button>

        <input
          type="range"
          className="sim-scrubber h-1.5 min-w-[80px] flex-1"
          min={0}
          max={Math.max(1, Math.round(duration))}
          step={1}
          value={Math.min(duration, Math.round(tNow))}
          aria-label={t("simulation.replay.scrubber")}
          aria-valuetext={clock}
          onChange={(e) => engine.seek(Number(e.target.value))}
        />
        <span className="shrink-0 whitespace-nowrap text-xs font-medium tabular-nums text-foreground">
          {clock}
        </span>
        <Select
          value={String(status.speed)}
          onValueChange={(v) => engine.setSpeed(Number(v))}
        >
          <SelectTrigger
            size="sm"
            className="w-[104px] shrink-0"
            aria-label={t("simulation.replay.speed")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {engine.speedOptions.map((opt) => (
              <SelectItem key={opt.value} value={String(opt.value)}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div
          className="flex items-center rounded-md border border-border p-0.5"
          role="group"
          aria-label={t("simulation.replay.granularity")}
        >
          {GRANULARITIES.map((g) => (
            <button
              key={g}
              type="button"
              aria-pressed={status.granularity === g}
              onClick={() => engine.setGranularity(g)}
              className={cn(
                "rounded px-2 py-1 text-xs font-medium transition-colors",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--sim-info)]",
                status.granularity === g
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t(`simulation.replay.grain.${g}`)}
            </button>
          ))}
        </div>

        <dl
          className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
          aria-live="polite"
          aria-label={t("simulation.replay.counters")}
        >
          <Chip label={t("simulation.replay.active")} value={numberFmt.format(frame?.global.activeCases ?? 0)} />
          <Chip label={t("simulation.replay.queued")} value={numberFmt.format(frame?.global.queuedCases ?? 0)} tone="warning" />
          <Chip label={t("simulation.replay.completed")} value={numberFmt.format(frame?.global.completedCases ?? 0)} />
          <Chip
            label={t("simulation.replay.throughput")}
            value={`${numberFmt.format(Math.round(frame?.global.throughputPerHour ?? 0))}/h`}
          />
        </dl>
      </div>
    </div>
  );
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warning";
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "m-0 font-semibold tabular-nums",
          tone === "warning" ? "text-[var(--amber-700)]" : "text-foreground",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
