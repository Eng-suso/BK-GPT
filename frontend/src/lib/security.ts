type RuntimeAuthConfig = {
  DELIR_API_TOKEN?: string;
  DELIR_ADMIN_TOKEN?: string;
  DELIR_TENANT_ID?: string;
};

function runtimeConfig(): RuntimeAuthConfig {
  if (typeof window === "undefined") return {};
  return window as unknown as RuntimeAuthConfig;
}

function tenantId(): string {
  return runtimeConfig().DELIR_TENANT_ID || import.meta.env.VITE_DELIR_TENANT_ID || "local";
}

function apiToken(): string {
  return runtimeConfig().DELIR_API_TOKEN || import.meta.env.VITE_DELIR_API_TOKEN || "";
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
