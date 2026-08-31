import { useCallback, useMemo, useState } from "react";

/** One filterable facet: a label plus how to read the value(s) off a row. */
export type ListFilterDef<T> = {
  id: string;
  label: string;
  /** Value(s) this row contributes to the facet. */
  accessor: (row: T) => string | string[];
};

export type ListFilterOption = { value: string; label: string; count: number };

/** A ready-to-render filter menu, handed to `<ListToolbar filters={…} />`. */
export type ListFilterMenu = {
  id: string;
  label: string;
  options: ListFilterOption[];
  selected: string[];
  onChange: (next: string[]) => void;
};

export type UseListFilters<T> = {
  /** Menus for the toolbar. */
  menus: ListFilterMenu[];
  /** Row predicate — `true` when the row passes every active facet. */
  match: (row: T) => boolean;
  /** Total number of selected values across all facets. */
  activeCount: number;
  /** Clear every facet. */
  clear: () => void;
};

function toValues(raw: string | string[]): string[] {
  return (Array.isArray(raw) ? raw : [raw]).filter(Boolean);
}

/**
 * Client-side multi-select filtering for a workspace list. Options and their
 * counts are derived from the rows; selection lives in component state. Pair
 * with `usePagedList` (filter first, then page).
 */
export function useListFilters<T>(
  rows: T[],
  defs: ListFilterDef<T>[],
): UseListFilters<T> {
  const [selected, setSelected] = useState<Record<string, string[]>>({});

  const menus = useMemo<ListFilterMenu[]>(() => {
    return defs.map((def) => {
      const counts = new Map<string, number>();
      for (const row of rows) {
        for (const value of toValues(def.accessor(row))) {
          counts.set(value, (counts.get(value) ?? 0) + 1);
        }
      }
      const options = [...counts.entries()]
        .map(([value, count]) => ({ value, label: value, count }))
        .sort((a, b) => a.label.localeCompare(b.label));
      return {
        id: def.id,
        label: def.label,
        options,
        selected: selected[def.id] ?? [],
        onChange: (next: string[]) =>
          setSelected((prev) => ({ ...prev, [def.id]: next })),
      };
    });
  }, [rows, defs, selected]);

  const match = useCallback(
    (row: T) =>
      defs.every((def) => {
        const picked = selected[def.id];
        if (!picked || picked.length === 0) return true;
        return toValues(def.accessor(row)).some((v) => picked.includes(v));
      }),
    [defs, selected],
  );

  const activeCount = useMemo(
    () => Object.values(selected).reduce((sum, v) => sum + v.length, 0),
    [selected],
  );

  const clear = useCallback(() => setSelected({}), []);

  return { menus, match, activeCount, clear };
}
