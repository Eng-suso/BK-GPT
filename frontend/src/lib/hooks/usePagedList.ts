import { useCallback, useMemo, useState } from "react";

import { useDebouncedValue } from "./useDebouncedValue";

export type PagedList<T> = {
  search: string;
  setSearch: (value: string) => void;
  page: number;
  setPage: (page: number) => void;
  filtered: T[];
  pageRows: T[];
  pageCount: number;
  pageSize: number;
  range: { from: number; to: number; count: number };
};

export type UsePagedListOptions = {
  /** Rows per page (default 10). */
  pageSize?: number;
  /** Controlled search value — omit to keep it in local state. */
  search?: string;
  onSearchChange?: (value: string) => void;
  /** Controlled 1-based page — omit to keep it in local state. */
  page?: number;
  onPageChange?: (page: number) => void;
};

/**
 * Client-side search + pagination for a workspace list. Search and page can be
 * left in local state (default) or driven from the URL by passing the
 * controlled props. Changing the search always returns to page 1.
 */
export function usePagedList<T>(
  data: T[],
  filter: (item: T, query: string) => boolean,
  options: UsePagedListOptions = {},
): PagedList<T> {
  const {
    pageSize = 10,
    search: controlledSearch,
    onSearchChange,
    page: controlledPage,
    onPageChange,
  } = options;

  const isSearchControlled = controlledSearch !== undefined;
  const isPageControlled = controlledPage !== undefined;

  const [internalSearch, setInternalSearch] = useState("");
  const [internalPage, setInternalPage] = useState(1);

  const search = isSearchControlled ? controlledSearch : internalSearch;
  const page = isPageControlled ? controlledPage : internalPage;
  const query = useDebouncedValue(search.trim().toLowerCase(), 250);

  const setPage = useCallback(
    (value: number) => {
      if (isPageControlled) onPageChange?.(value);
      else setInternalPage(value);
    },
    [isPageControlled, onPageChange],
  );

  const setSearch = useCallback(
    (value: string) => {
      if (isSearchControlled) {
        onSearchChange?.(value);
      } else {
        setInternalSearch(value);
        setInternalPage(1);
      }
    },
    [isSearchControlled, onSearchChange],
  );

  const filtered = useMemo(
    () => (query ? data.filter((item) => filter(item, query)) : data),
    [data, query, filter],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(Math.max(1, page), pageCount);
  const pageRows = filtered.slice(
    (safePage - 1) * pageSize,
    safePage * pageSize,
  );

  return {
    search,
    setSearch,
    page: safePage,
    setPage,
    filtered,
    pageRows,
    pageCount,
    pageSize,
    range: {
      from: filtered.length === 0 ? 0 : (safePage - 1) * pageSize + 1,
      to: Math.min(safePage * pageSize, filtered.length),
      count: filtered.length,
    },
  };
}
