import { API_BASE } from "./api";
import { authHeaders } from "./security";

/** Thrown for any non-2xx response. `body` holds the parsed JSON error, if any. */
export class HttpError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.body = body;
  }
}

type HttpOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Add the `X-DeliR-Admin-Token` header (destructive workspace ops). */
  admin?: boolean;
};

function buildRequest(path: string, options: HttpOptions): Promise<Response> {
  const { body, headers, admin, ...rest } = options;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;

  return fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: authHeaders(
      {
        ...(body !== undefined && !isForm
          ? { "Content-Type": "application/json" }
          : {}),
        ...headers,
      },
      { admin },
    ),
    body:
      body === undefined
        ? undefined
        : isForm
          ? (body as FormData)
          : JSON.stringify(body),
  });
}

async function raise(response: Response): Promise<never> {
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    parsed = undefined;
  }
  throw new HttpError(
    response.status,
    `${response.status} ${response.statusText}`,
    parsed,
  );
}

/**
 * Single entry point to the backend. Components never call `fetch` directly —
 * feature `api.ts` modules build query/mutation hooks on top of this.
 */
export async function http<T>(path: string, options: HttpOptions = {}): Promise<T> {
  const response = await buildRequest(path, options);

  if (!response.ok) {
    await raise(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/**
 * Streaming variant — auth and error handling stay centralised, but the caller
 * owns `response.body` (NDJSON / SSE reads). Throws `HttpError` on a non-2xx
 * response, same as `http`.
 */
export async function httpStream(
  path: string,
  options: HttpOptions = {},
): Promise<Response> {
  const response = await buildRequest(path, options);

  if (!response.ok) {
    await raise(response);
  }

  return response;
}

/** Human-readable message from a backend error (`{detail}` / `{error:{message}}`). */
export function httpErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof HttpError) {
    const body = error.body;
    if (body && typeof body === "object") {
      if ("detail" in body && typeof body.detail === "string") {
        return body.detail;
      }
      const nested = (body as { error?: { message?: unknown } }).error;
      if (nested && typeof nested.message === "string") {
        return nested.message;
      }
    }
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}
