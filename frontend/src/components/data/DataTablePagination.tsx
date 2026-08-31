import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export type DataTablePaginationProps = {
  page: number;
  pageCount: number;
  totalLabel: string;
  onPageChange: (page: number) => void;
  /** Max numbered buttons shown (default 3). */
  windowSize?: number;
  /** Current rows-per-page — enables the size selector when set with the options. */
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
};

export function DataTablePagination({
  page,
  pageCount,
  totalLabel,
  onPageChange,
  windowSize = 3,
  pageSize,
  pageSizeOptions = [10, 25, 50],
  onPageSizeChange,
}: DataTablePaginationProps): React.JSX.Element {
  const { t } = useTranslation("common");
  const start = Math.max(
    1,
    Math.min(page - Math.floor(windowSize / 2), pageCount - windowSize + 1),
  );
  const pages = Array.from(
    { length: Math.min(windowSize, pageCount) },
    (_, i) => start + i,
  ).filter((p) => p >= 1 && p <= pageCount);

  const btn =
    "grid h-7 min-w-7 place-items-center rounded-md border border-border bg-card px-2 text-xs font-medium tabular-nums text-muted-foreground shadow-control disabled:opacity-40";

  return (
    <>
      <div className="flex items-center gap-3">
        {pageSize != null && onPageSizeChange && (
          <select
            aria-label={t("pagination.rowsPerPage")}
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="h-7 rounded-md border border-border bg-card px-1.5 text-xs font-medium tabular-nums text-muted-foreground shadow-control"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        )}
        <span>{totalLabel}</span>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={btn}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={t("pagination.previous")}
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
          aria-label={t("pagination.next")}
        >
          <ChevronRight className="size-3.5" />
        </button>
      </div>
    </>
  );
}
