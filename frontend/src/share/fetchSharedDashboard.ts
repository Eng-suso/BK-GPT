import { API_BASE } from "@/lib/api";
import { toOwnerDashboard, type OwnerDashboardData } from "@/features/process/handover/dashboardContract";

/** Il link non vale: inesistente, scaduto, disattivato o processo archiviato. */
export class InvalidShareLink extends Error {}

/**
 * Legge il cruscotto con il solo codice del link. Nessuna credenziale dello
 * studio: questa pagina non le conosce. Il codice viaggia in un'intestazione,
 * non nell'indirizzo, cosi' non finisce nei log.
 */
export async function fetchSharedDashboard(token: string): Promise<OwnerDashboardData> {
  const response = await fetch(`${API_BASE}/v1/shared/process-dashboard`, {
    headers: { "X-DeliR-Share-Token": token },
    cache: "no-store",
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
  if (response.status === 404) throw new InvalidShareLink();
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return toOwnerDashboard(await response.json());
}

/** Il codice sta dopo `#`: il browser non lo manda mai al server che serve la pagina. */
export function tokenFromHash(hash: string): string {
  return decodeURIComponent(hash.replace(/^#/, "")).trim();
}
