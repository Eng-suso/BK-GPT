import { cn } from "@/lib/utils";

/** The DeliR mark (the delir.it favicon) and the "DeliR." wordmark. One logo
 *  everywhere in the product, identical to the marketing site. */
export function DelirMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false" className={cn("size-7 shrink-0", className)}>
      <rect width="64" height="64" rx="16" fill="var(--brand-mark-tile)" />
      <path d="M17 16h15c11 0 18 6 18 16s-7 16-18 16H17V16zm11 8v16h4c6 0 9-3 9-8s-3-8-9-8h-4z" fill="var(--brand-mark-letter)" />
    </svg>
  );
}

export function DelirWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-semibold tracking-[-0.05em] text-[var(--brand-ink)] [font-family:var(--font-family-brand)]", className)}>
      DeliR<span className="text-[var(--brand-blue)]">.</span>
    </span>
  );
}

export function DelirLogo({ wordmark = true, className }: { wordmark?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)} aria-label="DeliR" role="img">
      <DelirMark />
      {wordmark && <DelirWordmark className="text-[19px]" />}
    </span>
  );
}
