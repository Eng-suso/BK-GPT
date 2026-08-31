import { useMemo, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type OnChangeFn,
  type Row,
} from "@tanstack/react-table";
import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/ui/table";

export type DataTableProps<T> = {
  columns: ColumnDef<T>[];
  data: T[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedRowId?: string | null;
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;
  isLoading?: boolean;
  skeletonRows?: number;
  /** Rendered in place of the table body when data is empty and not loading. */
  emptyState?: ReactNode;
  /** Footer slot (pagination). */
  footer?: ReactNode;
  className?: string;
};

export function DataTable<T>({
  columns,
  data,
  getRowId,
  onRowClick,
  selectedRowId,
  sorting,
  onSortingChange,
  isLoading = false,
  skeletonRows = 8,
  emptyState,
  footer,
  className,
}: DataTableProps<T>): React.JSX.Element {
  // TanStack Table is intentionally not React-Compiler memoizable; that is fine
  // here — the table instance is recreated each render by design.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: sorting ? { sorting } : undefined,
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualPagination: true,
  });

  const colCount = columns.length;
  const showEmpty = !isLoading && data.length === 0 && emptyState;

  const skeletonBody = useMemo(
    () =>
      Array.from({ length: skeletonRows }, (_, i) => (
        <TableRow key={`sk-${i}`} className="border-border/60">
          {columns.map((_, c) => (
            <TableCell key={c} className="h-14 px-4">
              <Skeleton className="h-3 w-[60%]" />
            </TableCell>
          ))}
        </TableRow>
      )),
    [columns, skeletonRows],
  );

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card",
        className,
      )}
    >
      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader className="[&_tr]:border-border">
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead
                      key={header.id}
                      aria-sort={
                        !canSort
                          ? undefined
                          : sorted === "asc"
                            ? "ascending"
                            : sorted === "desc"
                              ? "descending"
                              : "none"
                      }
                      className="h-auto bg-card px-4 py-3 text-micro font-semibold tracking-[0.04em] text-muted-foreground uppercase"
                    >
                      {canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="-mx-1 inline-flex items-center gap-1 rounded-sm px-1 py-0.5 uppercase select-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {sorted === "asc" ? (
                            <ChevronUp className="size-3 opacity-70" />
                          ) : sorted === "desc" ? (
                            <ChevronDown className="size-3 opacity-70" />
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-40" />
                          )}
                        </button>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                        </span>
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {isLoading ? (
              skeletonBody
            ) : showEmpty ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={colCount} className="p-0">
                  {emptyState}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row: Row<T>) => {
                const isSelected = selectedRowId === row.id;
                const activate = onRowClick
                  ? () => onRowClick(row.original)
                  : undefined;
                return (
                  <TableRow
                    key={row.id}
                    data-state={isSelected ? "selected" : undefined}
                    onClick={activate}
                    onKeyDown={
                      activate
                        ? (e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              activate();
                            }
                          }
                        : undefined
                    }
                    tabIndex={activate ? 0 : undefined}
                    aria-current={isSelected ? true : undefined}
                    className={cn(
                      "relative border-border/60 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                      onRowClick && "cursor-pointer",
                      isSelected
                        ? "bg-[var(--color-surface-selected)] hover:bg-[var(--color-surface-selected)]"
                        : "hover:bg-muted/40",
                    )}
                  >
                    {row.getVisibleCells().map((cell, ci) => (
                      <TableCell
                        key={cell.id}
                        className={cn(
                          "h-14 px-4 text-body-sm text-muted-foreground",
                          ci === 0 &&
                            isSelected &&
                            "before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:bg-primary before:content-['']",
                        )}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {footer && (
        <div className="flex items-center justify-between border-t border-border bg-card px-4 py-3 text-xs text-muted-foreground">
          {footer}
        </div>
      )}
    </div>
  );
}
