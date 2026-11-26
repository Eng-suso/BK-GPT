import { QueryClient } from "@tanstack/react-query";

import { HttpError } from "./http";

/** 408 e 429 dicono "riprova"; gli altri 4xx dicono "questa richiesta e' cosi'". */
const RETRYABLE_CLIENT_STATUS = new Set([408, 429]);

/** Il limite d'uso della prova e' un 429 che non passa riprovando: si ripristina con la sessione. */
function isUsageLimit(error: HttpError): boolean {
  const body = error.body as { error?: { code?: unknown } } | undefined;
  return body?.error?.code === "usage_limit_reached";
}

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof HttpError && isUsageLimit(error)) return false;
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
