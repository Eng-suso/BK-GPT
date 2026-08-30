import { cn } from "@/lib/utils";

export type Priority = "alta" | "media" | "bassa";

const STYLES: Record<Priority, string> = {
  alta: "bg-[var(--red-50)] text-[var(--color-status-danger)]",
  media: "bg-[var(--amber-50)] text-[var(--amber-700)]",
  bassa: "bg-[var(--green-50)] text-[var(--green-700)]",
};

const LABEL: Record<Priority, string> = {
  alta: "Alta",
  media: "Media",
  bassa: "Bassa",
};

export type PriorityTagProps = {
  priority: Priority;
  className?: string;
};

/**
 * Filled tag — reserved for categorical values scanned in a table
 * (priority, issue type). Not for status; see {@link StatusIndicator}.
 */
export function PriorityTag({
  priority,
  className,
}: PriorityTagProps): React.JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex h-[19px] items-center rounded-[5px] px-[7px] text-[10.5px] font-semibold",
        STYLES[priority],
        className,
      )}
    >
      {LABEL[priority]}
    </span>
  );
}
