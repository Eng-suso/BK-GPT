import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export type DataTablePaginationProps = {
  page: number;
  pageCount: number;
  totalLabel: string;
  onPageChange: (page: number) => void;
  /** Max numbered buttons shown (default 3). */
  windowSize?: number;
};

export function DataTablePagination({
  page,
  pageCount,
  totalLabel,
  onPageChange,
  windowSize = 3,
}: DataTablePaginationProps): React.JSX.Element {
  const start = Math.max(1, Math.min(page - Math.floor(windowSize / 2), pageCount - windowSize + 1));
  const pages = Array.from(
    { length: Math.min(windowSize, pageCount) },
    (_, i) => start + i,
  ).filter((p) => p >= 1 && p <= pageCount);

  const btn =
    "grid h-7 min-w-7 place-items-center rounded-md border border-border bg-card px-2 text-xs font-medium tabular-nums text-muted-foreground shadow-control disabled:opacity-40";

  return (
    <>
      <span>{totalLabel}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={btn}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Pagina precedente"
        >
          <ChevronLeft className="size-3.5" />
        </button>
        {pages.map((p) => (
          <button
            key={p}
            type="button"
            className={cn(
              btn,
              p === page && "border-primary bg-primary text-primary-foreground",
            )}
            aria-current={p === page ? "page" : undefined}
            onClick={() => onPageChange(p)}
          >
            {p}
          </button>
        ))}
        <button
          type="button"
          className={btn}
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label="Pagina successiva"
        >
          <ChevronRight className="size-3.5" />
        </button>
      </div>
    </>
  );
}
