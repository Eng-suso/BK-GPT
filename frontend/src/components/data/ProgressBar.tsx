import { cn } from "@/lib/utils";

export type ProgressBarProps = {
  /** 0–100 */
  value: number;
  /** Show the "%" label to the right. */
  showValue?: boolean;
  /** Track width in px (default 100). */
  width?: number;
  className?: string;
};

export function ProgressBar({
  value,
  showValue = true,
  width = 100,
  className,
}: ProgressBarProps): React.JSX.Element {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="block h-[5px] overflow-hidden rounded-full bg-border"
        style={{ width }}
      >
        <span
          className="block h-full rounded-full bg-primary"
          style={{ width: `${pct}%` }}
        />
      </span>
      {showValue && (
        <b className="min-w-[30px] text-xs font-semibold tabular-nums text-foreground">
          {pct}%
        </b>
      )}
    </span>
  );
}
