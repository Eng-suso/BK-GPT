import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatTone = "neutral" | "ok" | "warning" | "danger";

const VALUE_TONE: Record<StatTone, string> = {
  neutral: "text-foreground",
  ok: "text-foreground",
  warning: "text-[var(--amber-700)]",
  danger: "text-[var(--color-status-danger)]",
};

export type StatTileProps = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: StatTone;
  className?: string;
};

/**
 * A single KPI cell: uppercase caption, one prominent tabular-nums value, an
 * optional muted hint. Fixed rhythm so a grid of tiles lines up.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  className,
}: StatTileProps): React.JSX.Element {
  return (
    <div
      className={cn(
        "min-w-0 rounded-md border border-border bg-muted/40 px-2.5 py-2",
        className,
      )}
    >
      <span className="eyebrow block">{label}</span>
      <strong
        className={cn(
          "mt-1 block truncate text-sm font-semibold tabular-nums",
          VALUE_TONE[tone],
        )}
      >
        {value}
      </strong>
      {hint != null && (
        <span className="mt-0.5 block truncate text-[11px] leading-tight text-muted-foreground">
          {hint}
        </span>
      )}
    </div>
  );
}
