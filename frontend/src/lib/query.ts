import { QueryClient } from "@tanstack/react-query";

import { HttpError } from "./http";

/** 408 e 429 dicono "riprova"; gli altri 4xx dicono "questa richiesta e' cosi'". */
const RETRYABLE_CLIENT_STATUS = new Set([408, 429]);

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (
    error instanceof HttpError &&
    error.status >= 400 &&
    error.status < 500 &&
    !RETRYABLE_CLIENT_STATUS.has(error.status)
  ) {
    return false;
  }
  return failureCount < 1;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetry,
      refetchOnWindowFocus: false,
    },
  },
});
