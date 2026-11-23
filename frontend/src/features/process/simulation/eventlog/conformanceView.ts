import type { Conformance } from "./eventLogTypes";

/** Quanto i casi reali seguono il disegno, con le stesse tre fasce del confronto reale/simulato. */
export type Adherence = "close" | "calibrate" | "far";

export function adherence(share: number): Adherence {
  if (share >= 0.9) return "close";
  if (share >= 0.6) return "calibrate";
  return "far";
}

export type DeviationRow = {
  elementId: string;
  name: string;
  /** Casi in cui il passo e' stato fatto senza quelli che il disegno mette prima. */
  outOfOrder: number;
  /** Casi finiti con il disegno ancora in attesa di questo passo. */
  skipped: number;
  /** Quota dei casi analizzati toccati da almeno una delle due deviazioni. */
  share: number;
};

/**
 * Le deviazioni da mostrare: solo i passi con un nome (un gateway senza nome
 * non dice niente al process owner, e il suo scarto si ritrova sulle attivita'
 * accanto), dal piu' frequente.
 */
export function deviationRows(result: Conformance): DeviationRow[] {
  return result.deviations
    .filter((item) => item.name && item.name !== item.element_id)
    .map((item) => ({
      elementId: item.element_id,
      name: item.name,
      outOfOrder: item.executed_out_of_order,
      skipped: item.left_waiting,
      share: result.cases ? Math.max(item.executed_out_of_order, item.left_waiting) / result.cases : 0,
    }));
}

export type OffPathVariant = {
  steps: string[];
  cases: number;
  /** Nomi dei passi saltati o anticipati, per dire in una riga cosa non torna. */
  skipped: string[];
  early: string[];
  unmodeled: string[];
};

/** I percorsi reali che escono dal disegno, i piu' frequenti prima. */
export function offPathVariants(result: Conformance, limit = 5): OffPathVariant[] {
  const names = new Map(result.deviations.map((item) => [item.element_id, item.name] as const));
  // Un elemento senza nome (gateway, evento) non si mostra: lo scarto si vede sui passi accanto.
  const named = (ids: string[]) =>
    ids
      .map((id) => names.get(id))
      .filter((name, index, all): name is string => Boolean(name) && !ids.includes(name!) && all.indexOf(name) === index);
  return result.variants
    .filter((variant) => !variant.fits)
    .slice(0, limit)
    .map((variant) => ({
      steps: variant.activities,
      cases: variant.cases,
      skipped: named(variant.waiting),
      early: named(variant.out_of_order),
      unmodeled: variant.unmodeled,
    }));
}
