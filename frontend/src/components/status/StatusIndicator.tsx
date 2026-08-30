import { cn } from "@/lib/utils";

/** Semantic status tone. Mapped to DeliR domain-role colours. */
export type StatusTone = "ok" | "pending" | "warning" | "danger" | "neutral";

const DOT: Record<StatusTone, string> = {
  ok: "bg-[var(--color-status-success)]",
  pending: "bg-[var(--color-status-info)]",
  warning: "bg-[var(--color-status-warning)]",
  danger: "bg-[var(--color-status-danger)]",
  neutral: "bg-muted-foreground",
};

const TEXT: Record<StatusTone, string> = {
  ok: "text-foreground",
  pending: "text-foreground",
  warning: "text-[var(--amber-700)]",
  danger: "text-[var(--color-status-danger)]",
  neutral: "text-muted-foreground",
};

export type StatusIndicatorProps = {
  tone: StatusTone;
  label: string;
  className?: string;
};

/**
 * Status as a small dot + plain label — the enterprise-premium pattern.
 * Never a filled pill (see docs/design/).
 */
export function StatusIndicator({
  tone,
  label,
  className,
}: StatusIndicatorProps): React.JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-xs",
        TEXT[tone],
        className,
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full ring-3 ring-black/[0.035]",
          DOT[tone],
        )}
        aria-hidden
      />
      {label}
    </span>
  );
}
