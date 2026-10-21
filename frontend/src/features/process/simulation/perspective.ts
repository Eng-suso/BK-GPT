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
import type { SimulationInsights, TaskStat } from "./simulationResults";

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
  task: TaskStat;
  /** Quota dell'attesa totale del processo (attesa media x volume), 0-1. */
  share: number;
};

/**
 * Dove si accumula il lavoro: le attivita' con piu' attesa totale, con la loro
 * quota dell'attesa complessiva. Nessuna attesa misurata = nessuna riga, non
 * una riga a zero.
 */
export function queueHotspots(insights: SimulationInsights, limit = 3): QueueHotspot[] {
  const waiting = insights.tasks
    .map((task) => ({ task, total: task.avgWaitingSec * Math.max(task.volume, 0) }))
    .filter((row) => row.total > 0);
  const sum = waiting.reduce((acc, row) => acc + row.total, 0);
  if (sum <= 0) return [];
  return waiting
    .sort((a, b) => b.total - a.total || a.task.name.localeCompare(b.task.name))
    .slice(0, limit)
    .map((row) => ({ task: row.task, share: row.total / sum }));
}
