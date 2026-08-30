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
            <TableCell key={c} className="h-[62px] px-[18px]">
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
        "flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card",
        "shadow-[0_1px_3px_rgba(14,20,32,0.06),0_1px_2px_-1px_rgba(14,20,32,0.05)]",
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
                      className={cn(
                        "h-auto bg-card px-[18px] py-3 text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground",
                        canSort && "cursor-pointer select-none",
                      )}
                      onClick={
                        canSort
                          ? header.column.getToggleSortingHandler()
                          : undefined
                      }
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {canSort &&
                          (sorted === "asc" ? (
                            <ChevronUp className="size-3 opacity-70" />
                          ) : sorted === "desc" ? (
                            <ChevronDown className="size-3 opacity-70" />
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-40" />
                          ))}
                      </span>
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
                return (
                  <TableRow
                    key={row.id}
                    data-state={isSelected ? "selected" : undefined}
                    onClick={
                      onRowClick ? () => onRowClick(row.original) : undefined
                    }
                    className={cn(
                      "relative border-border/60",
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
                          "h-[62px] px-[18px] text-[13px] text-muted-foreground",
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
        <div className="flex items-center justify-between border-t border-border bg-card px-[18px] py-3 text-[12.5px] text-muted-foreground">
          {footer}
        </div>
      )}
    </div>
  );
}
