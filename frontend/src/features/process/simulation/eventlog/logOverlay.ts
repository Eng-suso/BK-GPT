import type { NodeDecoration } from "../canvas/SimulationCanvas";
import type { Fidelity } from "./realVsSimulated";

/**
 * Cosa un passo del wizard porta sul disegno: le decorazioni e la legenda che
 * le spiega. La legenda viaggia con le decorazioni, cosi' lo studio non deve
 * indovinare da quale passo vengono.
 */
export type LogOverlay = {
  items: NodeDecoration[];
  /** Chiavi i18n del titolo della legenda e del prefisso delle tre fasce. */
  legend: { label: string; levels: string };
};

export type OnLogOverlay = (overlay: LogOverlay | null) => void;

/** Il tono del badge per fascia, uguale per ogni overlay a tre fasce. */
export const FIDELITY_BADGE_TONE: Record<Fidelity, NodeDecoration["badgeTone"]> = { close: "neutral", calibrate: "warning", far: "danger" };
