/**
 * SIM-08b: un ritmo degli arrivi diverso per mese ("dicembre +40%, agosto
 * -50%"), sopra le fasce orarie o sugli arrivi esponenziali.
 *
 * Lo applica il runner DeliR moltiplicando il ritmo per il fattore del mese
 * (ops/prosimos/runner/arrival_bands.py). Senza fasce gli arrivi devono essere
 * esponenziali: il runner usa i periodi del calendario degli arrivi come fasce.
 */
import type { DistributionName } from "./simulationTypes";

/** `percent` è la variazione sul ritmo: +40 = il 40% di casi in più, -50 = la metà. */
export type ArrivalMonthDraft = { month: number; percent: number };
export type ArrivalMonthInput = { month: number; factor: number };
export type ArrivalMonthIssue = "month" | "duplicate" | "percent";

/** Il backend accetta fattori fino a 10: al più +900%. */
export const MAX_PERCENT = 900;

/** Il primo mese non ancora usato, a +20%. */
export function newArrivalMonth(existing: ArrivalMonthDraft[]): ArrivalMonthDraft {
  const used = new Set(existing.map((m) => m.month));
  const month = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].find((m) => !used.has(m)) ?? 1;
  return { month, percent: 20 };
}

export function arrivalMonthIssues(months: ArrivalMonthDraft[]): (ArrivalMonthIssue | null)[] {
  const seen = new Set<number>();
  return months.map(({ month, percent }) => {
    if (!(Number.isInteger(month) && month >= 1 && month <= 12)) return "month";
    if (seen.has(month)) return "duplicate";
    seen.add(month);
    return Number.isFinite(percent) && percent > -100 && percent <= MAX_PERCENT ? null : "percent";
  });
}

/** Senza fasce il ritmo per mese vale solo su arrivi esponenziali (un processo di Poisson). */
export function monthsNeedPoisson(months: ArrivalMonthDraft[] | undefined, hasBands: boolean, distribution: DistributionName): boolean {
  return Boolean(months?.length) && !hasBands && distribution !== "expon";
}

export function arrivalMonthsInput(months: ArrivalMonthDraft[]): ArrivalMonthInput[] {
  return months.map(({ month, percent }) => ({ month, factor: 1 + percent / 100 }));
}

export function sanitizeArrivalMonths(raw: unknown): ArrivalMonthDraft[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const kept = raw.filter((m): m is ArrivalMonthDraft => Boolean(m) && typeof m === "object"
    && typeof (m as ArrivalMonthDraft).month === "number" && typeof (m as ArrivalMonthDraft).percent === "number");
  return kept.length ? kept.slice(0, 12) : undefined;
}
