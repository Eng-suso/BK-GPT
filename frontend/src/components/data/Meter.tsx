import { cn } from "@/lib/utils";

export type MeterTone = "ok" | "warning" | "danger";

const FILL: Record<MeterTone, string> = {
  ok: "bg-primary",
  warning: "bg-[var(--color-status-warning)]",
  danger: "bg-[var(--color-status-danger)]",
};

export type MeterProps = {
  /** 0–100 */
  value: number;
  tone?: MeterTone;
  /** Show the "%" value on the right. */
  showValue?: boolean;
  /** Track height in px (default 6). */
  height?: number;
  className?: string;
};

/**
 * A full-width proportion bar with a semantic fill. Unlike `ProgressBar` this
 * stretches to its container and carries a tone — use it for utilisation /
 * load readouts.
 */
export function Meter({
  value,
  tone = "ok",
  showValue = true,
  height = 6,
  className,
}: MeterProps): React.JSX.Element {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <span
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        className="block flex-1 overflow-hidden rounded-full bg-muted"
        style={{ height }}
      >
        <span
          className={cn("block h-full rounded-full transition-[width]", FILL[tone])}
          style={{ width: `${pct}%` }}
        />
      </span>
      {showValue && (
        <b className="min-w-[36px] text-right text-xs font-semibold tabular-nums text-foreground">
          {Math.round(pct)}%
        </b>
      )}
    </span>
  );
}
