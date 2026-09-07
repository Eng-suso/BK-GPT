import type { AgentActivity } from "../types";

/**
 * Il progresso che il consulente vede.
 *
 * Il backend manda una riga per *fase di lavoro*, gia' scritta nel vocabolario
 * del consulente. Qui non si traduce piu' niente da nomi interni: la vecchia
 * versione, quando non riconosceva un nodo, ne mostrava il nome con gli
 * underscore sostituiti da spazi — cioe' `canvas_layout_consultant_agent`
 * diventava una riga di stato. Un evento senza etichetta ora viene scartato.
 */

/** Un aggiornamento di fase come arriva dallo stream. */
export type AgentProgressEvent = {
  activityId?: string;
  phase?: string;
  label: string;
  detail?: string;
  icon?: string;
};

/**
 * Legge un evento `activity` dello stream, o `null` se non e' presentabile.
 *
 * @param event - Evento NDJSON grezzo.
 */
export function readProgressEvent(event: {
  message?: unknown;
  content?: unknown;
  payload?: Record<string, unknown> | null;
}): AgentProgressEvent | null {
  const payload = event.payload ?? {};
  const label = String(
    payload.label ?? event.message ?? event.content ?? "",
  ).trim();
  if (!label) return null;

  const phase = typeof payload.phase === "string" ? payload.phase : undefined;
  const detail =
    typeof payload.detail === "string" && payload.detail.trim()
      ? payload.detail.trim()
      : undefined;
  const icon = typeof payload.icon === "string" ? payload.icon : undefined;
  const activityId =
    typeof payload.activity_id === "string" ? payload.activity_id : undefined;

  return { activityId, phase, label, detail, icon };
}

/**
 * Avanza la timeline: chiude il passo in corso e apre quello nuovo.
 *
 * Un evento che ripete la fase gia' in corso non produce una riga in piu' —
 * il consulente vede il tempo che scorre su quella riga, non la stessa frase
 * scritta sette volte.
 *
 * @param current - Timeline corrente.
 * @param event - Aggiornamento di fase.
 * @param now - Istante di arrivo, in millisecondi.
 */
export function nextAgentActivity(
  current: AgentActivity[] | undefined,
  event: AgentProgressEvent,
  now: number = Date.now(),
): AgentActivity[] {
  const existing = current || [];
  const running = existing.find((item) => item.status === "running");

  if (running && event.phase && running.phase === event.phase) {
    // Stessa fase, dettaglio nuovo (un'altra fonte, un'altra ricerca):
    // si aggiorna la riga, non se ne aggiunge una.
    if (!event.detail || running.detail === event.detail) return existing;
    return existing.map((item) =>
      item === running ? { ...item, detail: event.detail } : item,
    );
  }

  const closed = existing.map((item) =>
    item.status === "running"
      ? { ...item, status: "completed" as const, endedAtMs: now }
      : item,
  );

  return [
    ...closed,
    {
      key: event.activityId || `${event.phase || "phase"}-${now}`,
      phase: event.phase,
      label: event.label,
      detail: event.detail,
      icon: event.icon,
      status: "running",
      startedAtMs: now,
    },
  ];
}

/** Chiude la timeline quando il turno finisce. */
export function completeAgentActivity(
  current: AgentActivity[] | undefined,
  now: number = Date.now(),
): AgentActivity[] | undefined {
  if (!current || current.length === 0) return current;
  return current.map((item) =>
    item.status === "running"
      ? { ...item, status: "completed" as const, endedAtMs: now }
      : item,
  );
}

/** Durata di un passo: chiusa se il passo e' finito, viva se e' in corso. */
export function activityDurationMs(
  item: AgentActivity,
  now: number = Date.now(),
): number {
  return Math.max(0, (item.endedAtMs ?? now) - item.startedAtMs);
}

/** `12s`, `1:05` — la stessa forma che il consulente legge sul cronometro. */
export function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
