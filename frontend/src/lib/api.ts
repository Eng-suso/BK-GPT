const win = window as unknown as Record<string, string | undefined>;
const configuredApiBase = win.DELIR_API_BASE || import.meta.env.VITE_API_BASE_URL;

const LOCAL_BACKEND = "http://127.0.0.1:8000";
const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost"]);

type PageLocation = Pick<Location, "protocol" | "hostname" | "port">;

/**
 * Dove il frontend chiede i dati.
 *
 * Prima ogni pagina non servita da `127.0.0.1:8000` chiamava `127.0.0.1:8000`:
 * su un dominio vero significava chiamare il computer di chi apriva la pagina,
 * e l'app restava vuota. Adesso il backend locale si chiama solo da una pagina
 * locale (Vite in sviluppo, o un file aperto dal disco); ovunque altrove la
 * pagina parla con il dominio da cui e' arrivata.
 */
export function resolveApiBase(location: PageLocation, configured?: string): string {
  if (configured) return configured;
  if (location.protocol === "file:") return LOCAL_BACKEND;
  // Solo Vite usa una porta diversa dall'API. Gli stack Compose servono
  // frontend e backend sulla stessa origine (18000 / 28000): spedirli alla
  // 8000 leggerebbe per errore il database DEV.
  if (LOCAL_HOSTS.has(location.hostname) && location.port === "3030") return LOCAL_BACKEND;
  return "";
}

export const API_BASE = resolveApiBase(window.location, configuredApiBase);
