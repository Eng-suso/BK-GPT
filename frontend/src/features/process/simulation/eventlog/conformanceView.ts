import type { Conformance } from "./eventLogTypes";
import type { Fidelity } from "./realVsSimulated";

/**
 * Le fasce dell'aderenza. Stessi tre livelli (e colori) del confronto reale
 * contro simulato, soglie proprie: qui si misura una quota di casi, non uno
 * scarto di tempi.
 */
export const ADHERENCE_CLOSE = 0.9;
export const ADHERENCE_CALIBRATE = 0.6;
/** Quota di casi che escono da un passo: fino al 10% vicino, fino al 40% da rivedere. */
export const DEVIATION_CLOSE = 0.1;
export const DEVIATION_CALIBRATE = 0.4;

/** Quanto i casi reali seguono il disegno, dalla quota di casi conformi. */
export function adherence(share: number): Fidelity {
  if (share >= ADHERENCE_CLOSE) return "close";
  return share >= ADHERENCE_CALIBRATE ? "calibrate" : "far";
}

/** La fascia di un passo dalla quota di casi che ne escono, estremi compresi nella fascia piu' bassa. */
export function deviationLevel(share: number): Fidelity {
  if (share <= DEVIATION_CLOSE) return "close";
  return share <= DEVIATION_CALIBRATE ? "calibrate" : "far";
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
 * Gli elementi con un nome. Un gateway o un evento senza nome non dice niente
 * al process owner (il server ne rimanda l'id come nome): lo scarto si ritrova
 * sulle attivita' accanto.
 */
function namedDeviations(result: Conformance) {
  return result.deviations.filter((item) => item.name && item.name !== item.element_id);
}

/** Le deviazioni da mostrare, dal passo che tocca piu' casi. */
export function deviationRows(result: Conformance): DeviationRow[] {
  return namedDeviations(result).map((item) => ({
    elementId: item.element_id,
    name: item.name,
    outOfOrder: item.executed_out_of_order,
    skipped: item.left_waiting,
    share: result.cases ? item.cases_affected / result.cases : 0,
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
  const names = new Map(namedDeviations(result).map((item) => [item.element_id, item.name] as const));
  const named = (ids: string[]) => [...new Set(ids.flatMap((id) => names.get(id) ?? []))];
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
