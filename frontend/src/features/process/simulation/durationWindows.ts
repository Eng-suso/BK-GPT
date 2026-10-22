/**
 * SIM-33b: la durata di un'attività cambia con l'ora in cui inizia ("dopo le
 * 16 una pratica richiede il 30% in più").
 *
 * Arriva al backend con la config del task (`durationWindows`) come fattore
 * sulla durata; Prosimos 2.1 non lo sa fare e lo applica il runner DeliR
 * (ops/prosimos/runner/duration_windows.py). Conta l'ora d'inizio. Qui stanno
 * la bozza, cosa le manca per partire e la sua traduzione.
 */
import { overlapsTaken } from "./arrivalBands";
import { WEEKDAYS, type Weekday } from "./simulationTypes";

/** `percent`: quanto cambia la durata, +30 = il 30% in più, -20 = il 20% in meno. */
export type DurationWindowDraft = { fromDay: Weekday; toDay: Weekday; begin: string; end: string; percent: number };
export type DurationWindowInput = { fromDay: Weekday; toDay: Weekday; begin: string; end: string; factor: number };
export type DurationWindowIssue = "order" | "percent" | "overlap";

export const MAX_WINDOWS = 21;
/** Il fattore va da poco sopra 0 a 10 volte la durata: da -99% a +900%. */
export const MIN_PERCENT = -99;
export const MAX_PERCENT = 900;

export function newDurationWindow(existing: DurationWindowDraft[]): DurationWindowDraft {
  // Il caso tipico è la fine della giornata; una seconda fascia parte dal sabato.
  return existing.length === 0
    ? { fromDay: "MONDAY", toDay: "FRIDAY", begin: "16:00", end: "18:00", percent: 30 }
    : { fromDay: "SATURDAY", toDay: "SATURDAY", begin: "09:00", end: "13:00", percent: 20 };
}

/** Il problema di ogni fascia, nello stesso ordine; `overlap` se si sovrappone a una precedente. */
export function durationWindowIssues(windows: DurationWindowDraft[]): (DurationWindowIssue | null)[] {
  const taken: [number, number][] = [];
  return windows.map((window) => {
    if (!window.begin || !window.end || window.begin >= window.end) return "order";
    if (!(Number.isFinite(window.percent) && window.percent >= MIN_PERCENT && window.percent <= MAX_PERCENT)) return "percent";
    return overlapsTaken(window, taken) ? "overlap" : null;
  });
}

export function durationWindowsInput(windows: DurationWindowDraft[]): DurationWindowInput[] {
  return windows.map(({ fromDay, toDay, begin, end, percent }) => ({ fromDay, toDay, begin, end, factor: 1 + percent / 100 }));
}

/** Bozze lette da fuori: ciò che non torna si scarta, non rompe il pannello. */
export function sanitizeDurationWindows(raw: unknown): DurationWindowDraft[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const day = (d: unknown): d is Weekday => typeof d === "string" && (WEEKDAYS as readonly string[]).includes(d);
  const kept = raw.filter((w): w is DurationWindowDraft => Boolean(w) && typeof w === "object" && day(w.fromDay) && day(w.toDay)
    && typeof w.begin === "string" && typeof w.end === "string" && typeof w.percent === "number");
  return kept.length ? kept.slice(0, MAX_WINDOWS) : undefined;
}
