import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { OnChangeFn, SortingState } from "@tanstack/react-table";

/**
 * A workspace list screen's view state (search / sort / page / page size /
 * facet selection) held in the URL query string, so a refresh or a shared
 * link restores the exact view.
 *
 * Params: `q`, `sort` (`field` or `field:desc`), `page`, `size`,
 * and one repeated `f_<facetId>` per selected facet value.
 */
export type ListQueryState = {
  search: string;
  setSearch: (value: string) => void;
  sorting: SortingState;
  setSorting: OnChangeFn<SortingState>;
  page: number;
  setPage: (page: number) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  filters: Record<string, string[]>;
  setFilters: (next: Record<string, string[]>) => void;
  clearFilters: () => void;
};

const FILTER_PREFIX = "f_";

export function useListQueryState(defaultPageSize = 10): ListQueryState {
  const [params, setParams] = useSearchParams();

  const patch = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          mutate(next);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const search = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = Number(params.get("size")) || defaultPageSize;

  const sorting = useMemo<SortingState>(() => {
    const raw = params.get("sort");
    if (!raw) return [];
    const [id, dir] = raw.split(":");
    return id ? [{ id, desc: dir === "desc" }] : [];
  }, [params]);

  const filters = useMemo<Record<string, string[]>>(() => {
    const out: Record<string, string[]> = {};
    for (const key of params.keys()) {
      if (key.startsWith(FILTER_PREFIX)) {
        out[key.slice(FILTER_PREFIX.length)] = params.getAll(key);
      }
    }
    return out;
  }, [params]);

  const setSearch = useCallback(
    (value: string) =>
      patch((p) => {
        if (value) p.set("q", value);
        else p.delete("q");
        p.delete("page");
      }),
    [patch],
  );

  const setSorting = useCallback<OnChangeFn<SortingState>>(
    (updater) =>
      patch((p) => {
        const next =
          typeof updater === "function" ? updater(sorting) : updater;
        const first = next[0];
        if (first) p.set("sort", first.desc ? `${first.id}:desc` : first.id);
        else p.delete("sort");
        p.delete("page");
      }),
    [patch, sorting],
  );

  const setPage = useCallback(
    (next: number) =>
      patch((p) => {
        if (next > 1) p.set("page", String(next));
        else p.delete("page");
      }),
    [patch],
  );

  const setPageSize = useCallback(
    (size: number) =>
      patch((p) => {
        if (size === defaultPageSize) p.delete("size");
        else p.set("size", String(size));
        p.delete("page");
      }),
    [patch, defaultPageSize],
  );

  const setFilters = useCallback(
    (next: Record<string, string[]>) =>
      patch((p) => {
        for (const key of [...p.keys()]) {
          if (key.startsWith(FILTER_PREFIX)) p.delete(key);
        }
        for (const [id, values] of Object.entries(next)) {
          for (const value of values) p.append(`${FILTER_PREFIX}${id}`, value);
        }
        p.delete("page");
      }),
    [patch],
  );

  const clearFilters = useCallback(
    () =>
      patch((p) => {
        for (const key of [...p.keys()]) {
          if (key.startsWith(FILTER_PREFIX)) p.delete(key);
        }
        p.delete("page");
      }),
    [patch],
  );

  return {
    search,
    setSearch,
    sorting,
    setSorting,
    page,
    setPage,
    pageSize,
    setPageSize,
    filters,
    setFilters,
    clearFilters,
  };
}
