/** Semantic status tone. Mapped to DeliR domain-role colours. */
export type StatusTone = "ok" | "pending" | "warning" | "danger" | "neutral";

/** Tone → dot background class. Shared by every status readout. */
export const STATUS_DOT: Record<StatusTone, string> = {
  ok: "bg-[var(--color-status-success)]",
  pending: "bg-[var(--color-status-info)]",
  warning: "bg-[var(--color-status-warning)]",
  danger: "bg-[var(--color-status-danger)]",
  neutral: "bg-muted-foreground",
};
