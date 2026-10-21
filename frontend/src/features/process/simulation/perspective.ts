/**
 * SIM-21: Consultant View e Operations View sono due prospettive sullo stesso
 * stato (scenario, run, selezione). Cambiare prospettiva non modifica lo
 * scenario e non avvia un run: cambia solo cosa e' in primo piano.
 *
 * - Consulente: ipotesi, distribuzioni, provenienza, qualita' dei dati,
 *   intervalli, validazione ed export.
 * - Operations: salute del processo, obiettivi di servizio, code, costo e
 *   cosa provare, senza parametri del modello.
 */
import type { SimulationPanel } from "./useSimulationSection";

export type Perspective = "consultant" | "operations";

/** Parametro di query che porta la prospettiva; assente = consulente. */
export const PERSPECTIVE_PARAM = "perspective";

/** Pannelli che configurano il modello o i dati: solo per il consulente. */
export const CONSULTANT_ONLY_PANELS: readonly SimulationPanel[] = ["scenario", "scenarios", "eventLog"];

export function parsePerspective(value: string | null | undefined): Perspective {
  return value === "operations" ? "operations" : "consultant";
}

export function isPanelVisible(panel: SimulationPanel, perspective: Perspective): boolean {
  return perspective === "consultant" || !CONSULTANT_ONLY_PANELS.includes(panel);
}

/**
 * Il pannello da mostrare nella prospettiva. Un pannello del consulente resta
 * nell'URL e torna quando si rientra nella vista consulente.
 */
export function panelInPerspective(panel: SimulationPanel | null, perspective: Perspective): SimulationPanel | null {
  return panel && isPanelVisible(panel, perspective) ? panel : null;
}

export type QueueHotspot = {
  /** Elemento BPMN dell'attivita', quando il log lo riconosce. */
  el: string | null;
  name: string;
  avgWaitSec: number;
  count: number;
  /** Casi in coda in media nel run (pesata sul tempo), se misurata. */
  queueAvg: number | null;
  /** Quota dell'attesa totale del processo (attesa media x occorrenze), 0-1. */
  share: number;
};

const num = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;

/**
 * Dove si accumula il lavoro, dal riepilogo del run sul log completo
 * (`summary.byActivity`): le attivita' con piu' attesa totale e la loro quota
 * dell'attesa complessiva. Nessuna attesa misurata = nessuna riga, non una
 * riga a zero.
 */
export function queueHotspots(byActivity: readonly Record<string, unknown>[] | null | undefined, limit = 3): QueueHotspot[] {
  const rows = (byActivity ?? []).flatMap((row) => {
    const avgWaitSec = num((row.wait as { avg?: unknown } | undefined)?.avg) ?? 0;
    const count = Math.max(num(row.count) ?? 0, 0);
    const total = avgWaitSec * count;
    if (total <= 0) return [];
    const name = typeof row.name === "string" ? row.name : typeof row.el === "string" ? row.el : "—";
    return [{ el: typeof row.el === "string" ? row.el : null, name, avgWaitSec, count, queueAvg: num((row.queue as { avg?: unknown } | undefined)?.avg), total }];
  });
  const sum = rows.reduce((acc, row) => acc + row.total, 0);
  return rows
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name))
    .slice(0, limit)
    .map(({ total, ...row }) => ({ ...row, share: total / sum }));
}
