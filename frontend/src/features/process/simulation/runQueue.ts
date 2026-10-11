import type { TFunction } from "i18next";

import type { SimulationRun } from "./simulationTypes";

type QueueState = NonNullable<SimulationRun["queue"]>["state"] | undefined;

/**
 * Cosa dire mentre un run aspetta (P0.3): in coda con la sua posizione, oppure
 * in corso. Un run senza stato di coda (backend anteriore) e' "in corso".
 * Riceve valori semplici: il React Compiler non deve pensare che il run cambi.
 */
export function runWaitTitle(state: QueueState, position: number | null | undefined, t: TFunction): string {
  if (state === "queued" && position) return t("simulation.queue.queued", { position });
  return t("simulation.running");
}

/** La riga sotto il titolo: perche' aspetta e che si puo' fare intanto. */
export function runWaitHint(state: QueueState, t: TFunction): string | undefined {
  return state === "queued" ? t("simulation.queue.queuedHint") : undefined;
}
