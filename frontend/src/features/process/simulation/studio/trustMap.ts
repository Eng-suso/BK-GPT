/**
 * SIM-20: quanto ci si puo' fidare di ogni elemento del run, per la lente
 * "Affidabilita'" della heatmap. Per ogni attivita' e decisione del modello IR
 * che il run ha simulato: il parametro piu' debole (origine, confidenza,
 * fonti) e, se c'e' un log reale mappato, lo scarto della lavorazione.
 *
 * La validazione sul log vince sulla confidenza dichiarata: un'attivita'
 * "alta" che nel log dura il doppio e' da calibrare, una "bassa" che nel log
 * torna e' validata. Confidenza e scarto restano entrambi leggibili.
 *
 * Pura: niente IO, niente React.
 */
import type { ActivityGap, Fidelity } from "../eventlog/realVsSimulated";
import type { Confidence, FieldOrigin, FieldProvenance } from "../simulationProvenance";
import type { ScenarioElementProvenance, ScenarioTemplate } from "../simulationTypes";
import { elementFromModel } from "./modelParameters";
import type { RunModel } from "./runModel";

export type TrustStatus = "calibrate" | "weak" | "toConfirm" | "solid" | "validated";

/** Prima cio' che chiede un intervento. */
export const TRUST_ORDER: readonly TrustStatus[] = ["calibrate", "weak", "toConfirm", "solid", "validated"];

export const TRUST_MARKER: Record<TrustStatus, string> = {
  calibrate: "sim-trust-calibrate",
  weak: "sim-trust-weak",
  toConfirm: "sim-trust-partial",
  solid: "sim-trust-solid",
  validated: "sim-trust-validated",
};

export type TrustRow = {
  el: string;
  name: string;
  kind: "activity" | "gateway";
  status: TrustStatus;
  /** Il parametro piu' debole dell'elemento. */
  confidence: Confidence;
  origin: FieldOrigin;
  /** Fonti distinte a sostegno dei parametri dell'elemento. */
  sources: number;
  /** Quanti parametri (assegnazioni o rami) ha l'elemento. */
  parameters: number;
  /** Scarto relativo della lavorazione simulata dal log reale, se misurato. */
  gap: number | null;
  fidelity: Fidelity | null;
};

const RANK: Record<Confidence, number> = { low: 0, medium: 1, high: 2 };

function weakest(items: FieldProvenance[]): FieldProvenance | null {
  return items.reduce<FieldProvenance | null>((acc, item) => (!acc || RANK[item.confidence] < RANK[acc.confidence] ? item : acc), null);
}

function statusOf(confidence: Confidence, fidelity: Fidelity | null): TrustStatus {
  if (fidelity === "close") return "validated";
  if (fidelity === "calibrate" || fidelity === "far") return "calibrate";
  return confidence === "low" ? "weak" : confidence === "medium" ? "toConfirm" : "solid";
}

function sourceCount(items: FieldProvenance[]): number {
  const keys = new Set<string>();
  for (const item of items) for (const source of item.sources ?? []) keys.add(`${source.kind}:${source.id}`);
  return keys.size;
}

export function trustMap(
  model: RunModel,
  provenance: readonly ScenarioElementProvenance[] = [],
  template: ScenarioTemplate | null = null,
  gaps: readonly ActivityGap[] = [],
): TrustRow[] {
  const elements = new Map(provenance.map((el) => [el.element_id, el]));
  const byEl = new Map(gaps.map((gap) => [gap.el, gap]));
  const ids = [
    ...model.activities.map((a) => ({ id: a.element_id, name: a.name || a.element_id })),
    ...model.gateways.map((g) => ({ id: g.element_id, name: template?.gateways.find((t) => t.element_id === g.element_id)?.name || g.element_id })),
  ];
  const rows: TrustRow[] = [];
  for (const { id, name } of ids) {
    const view = elementFromModel(model, id, elements.get(id), template);
    if (!view) continue;
    const items = view.kind === "activity" ? view.assignments.map((a) => a.provenance) : view.branches.map((b) => b.provenance);
    const weak = weakest(items.length ? items : view.kind === "gateway" ? [view.provenance] : []);
    if (!weak) continue;
    const gap = view.kind === "activity" ? byEl.get(id) : undefined;
    const fidelity = gap?.fidelity ?? null;
    rows.push({
      el: id, name, kind: view.kind, status: statusOf(weak.confidence, fidelity), confidence: weak.confidence, origin: weak.origin,
      sources: sourceCount(items), parameters: items.length, gap: gap?.processingGap ?? null, fidelity,
    });
  }
  return rows.sort((a, b) => TRUST_ORDER.indexOf(a.status) - TRUST_ORDER.indexOf(b.status) || a.name.localeCompare(b.name));
}

/** Quanti elementi per stato, in ordine di intervento. */
export function trustCounts(rows: readonly TrustRow[]): { status: TrustStatus; count: number }[] {
  return TRUST_ORDER.map((status) => ({ status, count: rows.filter((row) => row.status === status).length })).filter((row) => row.count > 0);
}
