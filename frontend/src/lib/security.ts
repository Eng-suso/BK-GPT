type RuntimeAuthConfig = {
  DELIR_API_TOKEN?: string;
  DELIR_ADMIN_TOKEN?: string;
  DELIR_TENANT_ID?: string;
};

const TOKEN_KEY = "delir:session-api-token";
const TENANT_KEY = "delir:session-tenant-id";
let memoryCredentials: { token: string; tenant: string } | null = null;

function sessionValue(key: string): string {
  try { return window.sessionStorage.getItem(key) ?? ""; }
  catch { return ""; }
}

/** Credentials supplied by the user for this browser origin and session. */
export function setSessionCredentials(token: string, tenant: string): void {
  memoryCredentials = { token, tenant };
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
    window.sessionStorage.setItem(TENANT_KEY, tenant);
  } catch { /* In-memory credentials still work for this page. */ }
}

export function clearSessionCredentials(): void {
  memoryCredentials = null;
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(TENANT_KEY);
  } catch { /* Storage can be unavailable in private browsing. */ }
}

function runtimeConfig(): RuntimeAuthConfig {
  if (typeof window === "undefined") return {};
  return window as unknown as RuntimeAuthConfig;
}

function tenantId(): string {
  return memoryCredentials?.tenant || sessionValue(TENANT_KEY) || runtimeConfig().DELIR_TENANT_ID || import.meta.env.VITE_DELIR_TENANT_ID || "local";
}

function apiToken(): string {
  return memoryCredentials?.token || sessionValue(TOKEN_KEY) || runtimeConfig().DELIR_API_TOKEN || import.meta.env.VITE_DELIR_API_TOKEN || "";
}

function adminToken(): string {
  return runtimeConfig().DELIR_ADMIN_TOKEN || import.meta.env.VITE_DELIR_ADMIN_TOKEN || "";
}

export function authHeaders(
  headers?: HeadersInit,
  options: { admin?: boolean } = {},
): Headers {
  const next = new Headers(headers);
  const token = apiToken();

  next.set("X-DeliR-Tenant-ID", tenantId());
  if (token) {
    next.set("Authorization", `Bearer ${token}`);
  }

  if (options.admin) {
    const admin = adminToken();
    if (admin) {
      next.set("X-DeliR-Admin-Token", admin);
    }
  }

  return next;
}

export function appendAuthQueryParams(url: URL): URL {
  const token = apiToken();

  url.searchParams.set("tenant_id", tenantId());
  if (token) {
    url.searchParams.set("api_token", token);
  }

  return url;
}
