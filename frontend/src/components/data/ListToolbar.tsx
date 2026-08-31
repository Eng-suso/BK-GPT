import { useTranslation } from "react-i18next";
import { ChevronDown, Search, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ListFilterMenu } from "@/lib/hooks/useListFilters";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";

export type { ListFilterMenu };

export function ListToolbar({
  search,
  onSearchChange,
  searchPlaceholder,
  filters = [],
  onClearFilters,
  className,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  /** Multi-select facet menus, e.g. from `useListFilters`. */
  filters?: ListFilterMenu[];
  /** Rendered as a "clear all" affordance when any facet is active. */
  onClearFilters?: () => void;
  className?: string;
}): React.JSX.Element {
  const { t } = useTranslation("common");
  const activeCount = filters.reduce((sum, f) => sum + f.selected.length, 0);

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="flex h-8 w-52 items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-muted-foreground shadow-control">
        <Search className="size-3.5" />
        <input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          className="w-full bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>

      {filters.map((filter) => (
        <FilterMenu key={filter.id} filter={filter} />
      ))}

      {activeCount > 0 && onClearFilters && (
        <button
          type="button"
          onClick={onClearFilters}
          className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <X className="size-3" />
          {t("actions.clearFilters")}
        </button>
      )}
    </div>
  );
}

function FilterMenu({ filter }: { filter: ListFilterMenu }): React.JSX.Element {
  const { t } = useTranslation("common");
  const active = filter.selected.length;

  const toggle = (value: string, checked: boolean): void => {
    filter.onChange(
      checked
        ? [...filter.selected, value]
        : filter.selected.filter((v) => v !== value),
    );
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "inline-flex h-8 items-center gap-1.5 rounded-lg border bg-card px-2.5 text-xs font-medium shadow-control transition-colors outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-muted/40",
          active
            ? "border-primary/40 text-foreground"
            : "border-border text-muted-foreground",
        )}
      >
        {filter.label}
        {active > 0 && (
          <span className="grid min-w-4 place-items-center rounded-full bg-primary px-1 text-2xs font-semibold text-primary-foreground tabular-nums">
            {active}
          </span>
        )}
        <ChevronDown className="size-3 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-72 w-56">
        <DropdownMenuLabel className="text-micro font-semibold tracking-[0.04em] text-muted-foreground uppercase">
          {filter.label}
        </DropdownMenuLabel>
        {filter.options.length === 0 ? (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">—</div>
        ) : (
          filter.options.map((opt) => (
            <DropdownMenuCheckboxItem
              key={opt.value}
              checked={filter.selected.includes(opt.value)}
              onSelect={(e) => e.preventDefault()}
              onCheckedChange={(checked) => toggle(opt.value, checked)}
              className="text-xs"
            >
              <span className="truncate">{opt.label}</span>
              <span className="ml-auto pl-2 text-2xs text-muted-foreground tabular-nums">
                {opt.count}
              </span>
            </DropdownMenuCheckboxItem>
          ))
        )}
        {active > 0 && (
          <>
            <DropdownMenuSeparator />
            <button
              type="button"
              onClick={() => filter.onChange([])}
              className="w-full rounded-sm px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            >
              {t("actions.clearFilter")}
            </button>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
