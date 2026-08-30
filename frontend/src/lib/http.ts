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

type HttpOptions = Omit<RequestInit, "body"> & { body?: unknown };

/**
 * Single entry point to the backend. Components never call `fetch` directly —
 * feature `api.ts` modules build query/mutation hooks on top of this.
 */
export async function http<T>(path: string, options: HttpOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options;

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: authHeaders({
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
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

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
