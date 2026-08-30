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

/**
 * Client-side search + pagination for a workspace list. Resets to page 1
 * on every search change.
 */
export function usePagedList<T>(
  data: T[],
  filter: (item: T, query: string) => boolean,
  pageSize = 10,
): PagedList<T> {
  const [search, setSearchRaw] = useState("");
  const [page, setPage] = useState(1);
  const query = useDebouncedValue(search.trim().toLowerCase(), 250);

  const setSearch = useCallback((value: string) => {
    setSearchRaw(value);
    setPage(1);
  }, []);

  const filtered = useMemo(
    () => (query ? data.filter((item) => filter(item, query)) : data),
    [data, query, filter],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);
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
      from: (safePage - 1) * pageSize + 1,
      to: Math.min(safePage * pageSize, filtered.length),
      count: filtered.length,
    },
  };
}
