/**
 * Il periodo di lavoro: quali incarichi si stanno guardando.
 *
 * Nella barra in alto c'era una data scritta nel codice ("01 mag – 31 lug
 * 2024") che non filtrava niente. Un intervallo mostrato accanto ai numeri
 * dice al consulente che quei numeri sono di quel periodo: se non e' vero, i
 * numeri sono sbagliati anche quando sono giusti.
 */

export const PERIOD_IDS = ["all", "month", "quarter", "year"] as const;
export type PeriodId = (typeof PERIOD_IDS)[number];

/** Nessun filtro: e' cio' che il prodotto ha sempre mostrato, e resta il default. */
export const DEFAULT_PERIOD: PeriodId = "all";

export type PeriodRange = {
  /** Inclusivo, in ISO `YYYY-MM-DD`. `null` quando il periodo non ha inizio. */
  from: string | null;
  /** Inclusivo. `null` quando il periodo non ha fine. */
  to: string | null;
};

function iso(date: Date): string {
  // Data locale, non UTC: chi guarda "questo mese" intende il proprio mese.
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * L'intervallo che un periodo copre adesso.
 *
 * @param period - Il periodo scelto
 * @param now - Il momento da cui si contano i periodi relativi (per i test)
 */
export function periodRange(period: PeriodId, now: Date = new Date()): PeriodRange {
  if (period === "all") return { from: null, to: null };

  if (period === "month") {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    return { from: iso(start), to: iso(end) };
  }

  if (period === "quarter") {
    const firstMonth = Math.floor(now.getMonth() / 3) * 3;
    const start = new Date(now.getFullYear(), firstMonth, 1);
    const end = new Date(now.getFullYear(), firstMonth + 3, 0);
    return { from: iso(start), to: iso(end) };
  }

  const start = new Date(now.getFullYear(), 0, 1);
  const end = new Date(now.getFullYear(), 11, 31);
  return { from: iso(start), to: iso(end) };
}

/**
 * Se un incarico tocca il periodo.
 *
 * Si guarda la sovrapposizione, non la data di inizio: un progetto cominciato a
 * gennaio e ancora aperto e' lavoro di questo mese, e nasconderlo farebbe
 * sparire proprio gli incarichi lunghi, che sono quelli che contano.
 *
 * Un progetto senza date resta visibile: "non l'ho detto" non e' "fuori
 * periodo", e togliere un record perche' un campo e' vuoto e' il modo piu'
 * rapido di far sparire lavoro vero da un elenco.
 */
export function overlapsPeriod(
  item: { startDate?: string | null; endDate?: string | null },
  range: PeriodRange,
): boolean {
  if (!range.from && !range.to) return true;

  const start = item.startDate || null;
  const end = item.endDate || null;
  if (!start && !end) return true;

  if (range.to && start && start > range.to) return false;
  if (range.from && end && end < range.from) return false;
  return true;
}
