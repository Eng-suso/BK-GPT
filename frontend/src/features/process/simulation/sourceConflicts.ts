import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, SimulationClaims } from "./simulationTypes";

/**
 * SIM-17: le fonti che dicono cose diverse sulla durata della stessa attivita'.
 *
 * Per ogni attivita' si mettono accanto la durata scritta nel pannello (se il
 * consulente l'ha toccata), quelle citate nei file del cliente e quella media
 * del log reale. Se la piu' lunga supera la piu' corta di oltre il 25% (la
 * soglia "da calibrare" del confronto reale contro simulato) il disaccordo
 * diventa una domanda da fare al cliente. Nessuna fonte vince da sola.
 */

export const CONFLICT_SPREAD = 0.25;

export type DurationSourceKind = "panel" | "claim" | "log";

export type DurationSource = { kind: DurationSourceKind; label: string; seconds: number };

export type SourceConflict = {
  elementId: string;
  name: string;
  sources: DurationSource[];
  shortest: DurationSource;
  longest: DurationSource;
  /** (piu' lunga - piu' corta) / piu' corta. */
  spread: number;
};

/** La durata media scritta nel pannello: per l'uniforme il punto medio, come nella richiesta. */
function panelSeconds(task: ScenarioDraft["tasks"][string]): number {
  const minutes = task.distribution === "uniform" && task.minMinutes !== undefined && task.maxMinutes !== undefined
    ? (task.minMinutes + task.maxMinutes) / 2
    : task.meanMinutes;
  return minutes * 60;
}

export function sourceConflicts({
  template,
  draft,
  claims,
  realProcessing,
  logName,
  panelLabel,
}: {
  template: ScenarioTemplate | null;
  draft: ScenarioDraft;
  claims: SimulationClaims | null;
  realProcessing: Map<string, { seconds: number }> | null;
  logName: string;
  panelLabel: string;
}): SourceConflict[] {
  const proposalsByEl = new Map((claims?.activities ?? []).map((a) => [a.element_id, a.proposals]));
  const conflicts: SourceConflict[] = [];
  for (const task of template?.tasks ?? []) {
    const cfg = draft.tasks[task.element_id];
    const sources: DurationSource[] = [];
    // Un valore lasciato al predefinito non e' una fonte: nessuno l'ha detto.
    if (cfg && cfg.meanMinutes !== draft.defaultTaskMinutes) {
      sources.push({ kind: "panel", label: panelLabel, seconds: panelSeconds(cfg) });
    }
    const dismissed = new Set(draft.dismissedClaims?.[task.element_id] ?? []);
    for (const proposal of proposalsByEl.get(task.element_id) ?? []) {
      if (proposal.duration_hint && !dismissed.has(proposal.claim_id)) {
        sources.push({ kind: "claim", label: proposal.source_name, seconds: proposal.duration_hint.seconds });
      }
    }
    const real = realProcessing?.get(task.element_id);
    if (real && real.seconds > 0) sources.push({ kind: "log", label: logName, seconds: real.seconds });

    const valid = sources.filter((s) => Number.isFinite(s.seconds) && s.seconds > 0);
    if (valid.length < 2) continue;
    const shortest = valid.reduce((a, b) => (b.seconds < a.seconds ? b : a));
    const longest = valid.reduce((a, b) => (b.seconds > a.seconds ? b : a));
    const spread = (longest.seconds - shortest.seconds) / shortest.seconds;
    if (spread > CONFLICT_SPREAD) {
      conflicts.push({ elementId: task.element_id, name: task.name || task.element_id, sources: valid, shortest, longest, spread });
    }
  }
  // Prima i disaccordi piu' larghi: sono le domande che spostano di piu' il modello.
  return conflicts.sort((a, b) => b.spread - a.spread);
}
