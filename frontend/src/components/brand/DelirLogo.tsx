import { cn } from "@/lib/utils";

/** The DeliR wordmark, as on delir.it: "DeliR" in the brand ink with the blue
 *  period. `compact` keeps only "D." for the narrow rail. Type only, no tile:
 *  the product chrome stays light and quiet. */
export function DelirLogo({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <span
      role="img"
      aria-label="DeliR"
      className={cn(
        "inline-flex items-baseline font-semibold leading-none tracking-[-0.05em] text-[var(--brand-ink)] [font-family:var(--font-family-brand)]",
        compact ? "text-[22px]" : "text-[21px]",
        className,
      )}
    >
      <span aria-hidden>{compact ? "D" : "DeliR"}</span>
      <span aria-hidden className="text-[var(--brand-blue)]">.</span>
    </span>
  );
}
