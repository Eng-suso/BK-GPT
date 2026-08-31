import React from "react";

import { cn } from "@/lib/utils";

export type AsOfRow = {
  id: string;
  label: string;
  /** primary value that drives bar length + sort */
  value: number;
  /** optional secondary value stacked on the same track (e.g. queued vs active) */
  secondary?: number;
  formatted?: string;
};

type AsOfBarListProps = {
  title: string;
  rows: AsOfRow[];
  /** CSS colour for the primary segment. */
  color: string;
  /** CSS colour for the secondary segment. */
  secondaryColor?: string;
  legend?: { primary: string; secondary?: string };
  /** Fixed scale max; falls back to the largest current total. */
  max?: number;
  formatValue?: (value: number) => string;
};

/**
 * "Value right now" per activity / resource — a compact bar-row list (the Meter
 * idiom), re-sorted by the primary value each frame. No chart library needed for
 * these short lists.
 */
export function AsOfBarList({
  title,
  rows,
  color,
  secondaryColor,
  legend,
  max,
  formatValue = (v) => String(Math.round(v)),
}: AsOfBarListProps): React.JSX.Element {
  const sorted = React.useMemo(
    () =>
      [...rows].sort(
        (a, b) => b.value + (b.secondary ?? 0) - (a.value + (a.secondary ?? 0)),
      ),
    [rows],
  );
  const scale = Math.max(
    1,
    max ?? Math.max(...sorted.map((r) => r.value + (r.secondary ?? 0)), 1),
  );

  return (
    <figure className="m-0 flex min-w-0 flex-col rounded-lg border border-border bg-card p-3">
      <figcaption className="mb-2 flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{title}</span>
        {legend && (
          <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Swatch color={color} label={legend.primary} />
            {legend.secondary && secondaryColor && (
              <Swatch color={secondaryColor} label={legend.secondary} />
            )}
          </span>
        )}
      </figcaption>

      {sorted.length === 0 ? (
        <p className="py-2 text-xs text-muted-foreground">—</p>
      ) : (
        <ul className="grid gap-1.5">
          {sorted.map((row) => {
            const primaryPct = (row.value / scale) * 100;
            const secondaryPct = ((row.secondary ?? 0) / scale) * 100;
            return (
              <li
                key={row.id}
                className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_auto] items-center gap-2"
              >
                <span className="truncate text-xs text-foreground" title={row.label}>
                  {row.label}
                </span>
                <span
                  className="sim-barrow-track flex h-2"
                  role="img"
                  aria-label={`${row.label}: ${row.formatted ?? formatValue(row.value + (row.secondary ?? 0))}`}
                >
                  <span
                    className="sim-barrow-fill"
                    style={{ width: `${Math.max(primaryPct, row.value > 0 ? 3 : 0)}%`, background: color }}
                  />
                  {secondaryPct > 0 && secondaryColor && (
                    <span
                      className={cn("sim-barrow-fill", "ml-px")}
                      style={{ width: `${secondaryPct}%`, background: secondaryColor }}
                    />
                  )}
                </span>
                <span className="text-right text-xs font-medium tabular-nums text-foreground">
                  {row.formatted ?? formatValue(row.value + (row.secondary ?? 0))}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </figure>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="size-1.5 rounded-full" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}
