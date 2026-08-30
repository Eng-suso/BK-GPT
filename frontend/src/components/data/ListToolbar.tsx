import { ChevronDown, Search } from "lucide-react";

import { cn } from "@/lib/utils";

export type FilterChip = {
  id: string;
  label: string;
  onClick?: () => void;
};

export function ListToolbar({
  search,
  onSearchChange,
  searchPlaceholder,
  filters = [],
  className,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  filters?: FilterChip[];
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex h-8 w-52 items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-muted-foreground shadow-[0_1px_2px_rgba(14,20,32,0.05)]">
        <Search className="size-3.5" />
        <input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          className="w-full bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
      {filters.map((f) => (
        <button
          key={f.id}
          type="button"
          onClick={f.onClick}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 text-[12.5px] font-normal text-muted-foreground shadow-[0_1px_2px_rgba(14,20,32,0.05)] hover:bg-muted/40"
        >
          {f.label}
          <ChevronDown className="size-3 text-muted-foreground" />
        </button>
      ))}
    </div>
  );
}
