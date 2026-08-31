import { cn } from "@/lib/utils";
import { STATUS_DOT, type StatusTone } from "@/components/status";

export type ListSummaryItem = {
  label: string;
  count: number;
  /** Optional coloured dot. */
  tone?: StatusTone;
  /** Highlight state (e.g. this facet value is filtered on). */
  active?: boolean;
  /** Makes the segment a toggle. */
  onClick?: () => void;
};

/**
 * A compact "12 in corso · 3 a rischio · 2 bozza" readout under a list header.
 * Segments can be toggles that drive a facet filter.
 */
export function ListSummary({
  items,
  className,
}: {
  items: ListSummaryItem[];
  className?: string;
}): React.JSX.Element {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-1 gap-y-1 text-xs",
        className,
      )}
    >
      {items.map((item, i) => {
        const body = (
          <span className="inline-flex items-center gap-1.5">
            {item.tone && (
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  STATUS_DOT[item.tone],
                )}
                aria-hidden
              />
            )}
            <span className="font-semibold text-foreground tabular-nums">
              {item.count}
            </span>
            <span className="text-muted-foreground">{item.label}</span>
          </span>
        );
        return (
          <span key={item.label} className="inline-flex items-center">
            {i > 0 && (
              <span aria-hidden className="px-2 text-muted-foreground/50">
                ·
              </span>
            )}
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                aria-pressed={item.active}
                className={cn(
                  "rounded-sm px-1 py-0.5 transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  item.active && "bg-muted",
                )}
              >
                {body}
              </button>
            ) : (
              body
            )}
          </span>
        );
      })}
    </div>
  );
}
