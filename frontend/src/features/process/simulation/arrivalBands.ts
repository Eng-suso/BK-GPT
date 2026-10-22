/**
 * SIM-08: arrivi con un ritmo diverso per fascia oraria ("un caso ogni 5
 * minuti dalle 9 alle 12, ogni 30 il pomeriggio").
 *
 * Prosimos 2.1 non li sa generare: li genera il runner DeliR
 * (ops/prosimos/runner/arrival_bands.py). Fuori da ogni fascia non arriva
 * nessuno. Qui stanno la bozza, cosa le manca per partire e la sua traduzione.
 */
import type { CaseAttributeDraft } from "./caseRules";
import { WEEKDAYS, type Weekday } from "./simulationTypes";

/** Una fascia della settimana: da un giorno a un altro, fra due orari ``HH:MM``. */
export type WeeklyBand = { fromDay: Weekday; toDay: Weekday; begin: string; end: string };
export type ArrivalBandDraft = { fromDay: Weekday; toDay: Weekday; begin: string; end: string; meanMinutes: number };
export type ArrivalBandInput = { fromDay: Weekday; toDay: Weekday; begin: string; end: string; meanSeconds: number };
export type ArrivalBandIssue = "order" | "mean" | "overlap";

export const MAX_BANDS = 21;

export function newArrivalBand(existing: ArrivalBandDraft[]): ArrivalBandDraft {
  // La prima fascia e' il picco del mattino; le successive partono dal pomeriggio.
  return existing.length === 0
    ? { fromDay: "MONDAY", toDay: "FRIDAY", begin: "09:00", end: "12:00", meanMinutes: 5 }
    : { fromDay: "MONDAY", toDay: "FRIDAY", begin: "14:00", end: "17:00", meanMinutes: 30 };
}

/** Il problema di ogni fascia, nello stesso ordine; `overlap` se si sovrappone a una precedente. */
export function arrivalBandIssues(bands: ArrivalBandDraft[]): (ArrivalBandIssue | null)[] {
  const taken: [number, number][] = [];
  return bands.map((band) => {
    if (!band.begin || !band.end || band.begin >= band.end) return "order";
    if (!(Number.isFinite(band.meanMinutes) && band.meanMinutes > 0)) return "mean";
    return overlapsTaken(band, taken) ? "overlap" : null;
  });
}

/** Una fascia della settimana che si sovrappone a una gia' presa; la aggiunge a quelle prese. */
export function overlapsTaken(band: WeeklyBand, taken: [number, number][]): boolean {
  const spans = days(band).map((day): [number, number] => [day * 1440 + minutes(band.begin), day * 1440 + minutes(band.end)]);
  const overlaps = spans.some(([a, b]) => taken.some(([c, d]) => a < d && c < b));
  taken.push(...spans);
  return overlaps;
}

export function arrivalBandsInput(bands: ArrivalBandDraft[]): ArrivalBandInput[] {
  return bands.map(({ fromDay, toDay, begin, end, meanMinutes }) => ({
    fromDay, toDay, begin, end, meanSeconds: Math.max(1, Math.round(meanMinutes * 60)),
  }));
}

export function sanitizeArrivalBands(raw: unknown): ArrivalBandDraft[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const day = (d: unknown): d is Weekday => typeof d === "string" && (WEEKDAYS as readonly string[]).includes(d);
  const kept = raw.filter((b): b is ArrivalBandDraft => Boolean(b) && typeof b === "object" && day(b.fromDay) && day(b.toDay)
    && typeof b.begin === "string" && typeof b.end === "string" && typeof b.meanMinutes === "number");
  return kept.length ? kept.slice(0, MAX_BANDS) : undefined;
}

function days(band: WeeklyBand): number[] {
  const first = WEEKDAYS.indexOf(band.fromDay);
  const last = WEEKDAYS.indexOf(band.toDay);
  const all = [0, 1, 2, 3, 4, 5, 6];
  return first <= last ? all.slice(first, last + 1) : [...all.slice(first), ...all.slice(0, last + 1)];
}

function minutes(clock: string): number {
  const [h, m] = clock.split(":").map(Number);
  return h * 60 + m;
}

/**
 * SIM-33: la fascia di arrivo come attributo del caso. L'attributo lo tiene il
 * pannello (id fisso, categorie = fasce) e lo riempie il runner con la fascia in
 * cui ogni caso arriva; durate per categoria e regole lo usano come gli altri.
 */
export const BAND_ATTRIBUTE_ID = "arrival-band";
export const BAND_ATTRIBUTE_NAME = "fascia_arrivo";

/** La categoria della fascia ``index`` (da 0): la stessa che scrive il runner. */
export function bandLabel(index: number): string {
  return `Fascia ${index + 1}`;
}

/** Gli attributi del caso con quello della fascia allineato alle fasce, o senza se non serve. */
export function withBandAttribute(attributes: CaseAttributeDraft[], bands: ArrivalBandDraft[] | undefined, enabled: boolean): CaseAttributeDraft[] {
  const others = attributes.filter((a) => a.id !== BAND_ATTRIBUTE_ID);
  if (!enabled || !bands?.length) return others.length === attributes.length ? attributes : others;
  // Le quote non contano: il runner sovrascrive il valore con la fascia vera.
  const band: CaseAttributeDraft = {
    id: BAND_ATTRIBUTE_ID,
    name: BAND_ATTRIBUTE_NAME,
    kind: "category",
    categories: bands.map((_, i) => ({ value: bandLabel(i), percent: 100 / bands.length })),
  };
  const index = attributes.findIndex((a) => a.id === BAND_ATTRIBUTE_ID);
  return index < 0 ? [...attributes, band] : attributes.map((a, i) => (i === index ? band : a));
}
