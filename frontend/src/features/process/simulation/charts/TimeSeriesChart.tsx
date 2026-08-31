import React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ReplayEngine } from "../replay/replayEngine";
import { usePlayhead } from "../replay/useReplay";
import { CHART_INSET, axisProps, gridProps } from "./chartTheme";

export type TimeSeriesPoint = { t: number } & Record<string, number>;

export type TimeSeriesSeries = {
  key: string;
  label: string;
  /** CSS colour (a token var string). */
  color: string;
};

type TimeSeriesChartProps = {
  title: string;
  data: TimeSeriesPoint[];
  series: TimeSeriesSeries[];
  engine: ReplayEngine;
  /** tooltip value formatter */
  formatValue?: (value: number) => string;
  /** compact Y-axis tick formatter (defaults to `formatValue`) */
  formatAxisValue?: (value: number) => string;
  formatTime: (sec: number) => string;
  height?: number;
};

export function TimeSeriesChart({
  title,
  data,
  series,
  engine,
  formatValue = (v) => String(Math.round(v)),
  formatAxisValue,
  formatTime,
  height = 148,
}: TimeSeriesChartProps): React.JSX.Element {
  const durationSec = engine.durationSec;
  const tNow = usePlayhead(engine);
  const frac = Math.min(1, Math.max(0, durationSec ? tNow / durationSec : 0));

  return (
    <figure className="m-0 flex min-w-0 flex-col rounded-lg border border-border bg-card p-3">
      <figcaption className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{title}</span>
        {series.length === 1 && (
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ background: series[0].color }}
            aria-hidden
          />
        )}
      </figcaption>

      <div className="sim-chart overflow-x-auto" style={{ height }}>
        <ChartBody
          data={data}
          series={series}
          durationSec={durationSec}
          formatValue={formatValue}
          formatAxisValue={formatAxisValue ?? formatValue}
          formatTime={formatTime}
        />
        <div
          className="sim-chart-future"
          style={{ left: `calc(${CHART_INSET.left}px + ${frac} * (100% - ${CHART_INSET.left + CHART_INSET.right}px))` }}
          aria-hidden
        />
        <div
          className="sim-chart-playhead"
          style={{ left: `calc(${CHART_INSET.left}px + ${frac} * (100% - ${CHART_INSET.left + CHART_INSET.right}px))` }}
          aria-hidden
        />
      </div>
    </figure>
  );
}

type ChartBodyProps = {
  data: TimeSeriesPoint[];
  series: TimeSeriesSeries[];
  durationSec: number;
  formatValue: (value: number) => string;
  formatAxisValue: (value: number) => string;
  formatTime: (sec: number) => string;
};

/** Memoised: static props, so it renders once and the playhead moves over it. */
const ChartBody = React.memo(function ChartBody({
  data,
  series,
  durationSec,
  formatValue,
  formatAxisValue,
  formatTime,
}: ChartBodyProps): React.JSX.Element {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: CHART_INSET.top, right: CHART_INSET.right, bottom: 0, left: 0 }}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`sim-fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="var(--sim-chart-fill-opacity)" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid {...gridProps} />
        <XAxis
          dataKey="t"
          type="number"
          domain={[0, durationSec]}
          tickFormatter={formatTime}
          tickCount={4}
          {...axisProps}
        />
        <YAxis
          width={CHART_INSET.left}
          tickFormatter={(v) => formatAxisValue(Number(v))}
          {...axisProps}
        />
        <Tooltip
          isAnimationActive={false}
          cursor={{ stroke: "var(--sim-chart-axis)", strokeDasharray: "2 3" }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <div className="sim-chart-tooltip">
                <div className="font-medium">{formatTime(Number(label))}</div>
                {payload.map((p) => (
                  <div key={String(p.dataKey)} className="flex items-center gap-1.5">
                    <span
                      className="size-1.5 rounded-full"
                      style={{ background: p.color as string }}
                      aria-hidden
                    />
                    <span className="text-muted-foreground">
                      {series.find((s) => s.key === p.dataKey)?.label ??
                        String(p.dataKey)}
                    </span>
                    <span className="ml-auto font-medium tabular-nums">
                      {formatValue(Number(p.value))}
                    </span>
                  </div>
                ))}
              </div>
            ) : null
          }
        />
        {series.length > 1 && (
          <Legend
            verticalAlign="top"
            height={20}
            iconType="circle"
            iconSize={7}
            formatter={(value) => (
              <span className="text-[11px] text-muted-foreground">{value}</span>
            )}
          />
        )}
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            fill={`url(#sim-fill-${s.key})`}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
});
