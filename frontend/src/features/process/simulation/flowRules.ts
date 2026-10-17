/**
 * SIM-35: salto e rilavorazione di un'attività nel pannello scenario.
 *
 * Arrivano al backend con la config del task (`skip`, `rework`), come le
 * durate per categoria: il backend li scrive come decisioni per regola nel
 * BPMN del motore (backend/simulation/ir/flow_rules.py). Qui stanno la bozza,
 * cosa le manca per partire e la sua traduzione.
 */
import { irCondition, isRuleGroups, ruleIssue, type BranchRuleDraft, type CaseAttributeDraft, type IrCondition } from "./caseRules";

/** Una quota dei casi salta l'attività; con `rule`, la quota dei soli casi che la soddisfano. */
export type SkipDraft = { percent: number; rule?: BranchRuleDraft };
/** Finita l'attività, una quota torna a `backTo` e rifà il lavoro, al più `maxRepeats` volte. */
export type ReworkDraft = { backTo: string; percent: number; maxRepeats: number; rule?: BranchRuleDraft };

export const MAX_REPEATS = 10;

export type FlowRuleIssue = "skipPercent" | "reworkPercent" | "reworkTarget" | "reworkRepeats" | "rule";

export type SkipInput = { probability: number; condition?: IrCondition };
export type ReworkInput = { backTo: string; probability: number; maxRepeats: number; condition?: IrCondition };

export function skipIssue(skip: SkipDraft, attributes: CaseAttributeDraft[]): FlowRuleIssue | null {
  if (!(Number.isFinite(skip.percent) && skip.percent > 0 && skip.percent <= 100)) return "skipPercent";
  return skip.rule && ruleIssue(skip.rule, attributes) !== null ? "rule" : null;
}

/** `activityIds`: le attività del processo, fra cui deve stare quella da cui si riparte. */
export function reworkIssue(rework: ReworkDraft, attributes: CaseAttributeDraft[], activityIds: ReadonlySet<string>): FlowRuleIssue | null {
  // Sempre indietro sarebbe un ciclo senza uscita fino al tetto: il 100% non ha senso.
  if (!(Number.isFinite(rework.percent) && rework.percent > 0 && rework.percent < 100)) return "reworkPercent";
  if (!activityIds.has(rework.backTo)) return "reworkTarget";
  if (!(Number.isInteger(rework.maxRepeats) && rework.maxRepeats >= 1 && rework.maxRepeats <= MAX_REPEATS)) return "reworkRepeats";
  return rework.rule && ruleIssue(rework.rule, attributes) !== null ? "rule" : null;
}

export function skipInput(skip: SkipDraft, attributes: CaseAttributeDraft[]): SkipInput {
  return {
    probability: skip.percent / 100,
    ...(skip.rule ? { condition: irCondition(skip.rule, attributes) } : {}),
  };
}

export function reworkInput(rework: ReworkDraft, attributes: CaseAttributeDraft[]): ReworkInput {
  return {
    backTo: rework.backTo,
    probability: rework.percent / 100,
    maxRepeats: rework.maxRepeats,
    ...(rework.rule ? { condition: irCondition(rework.rule, attributes) } : {}),
  };
}

/** Gli attributi che salti e rilavorazioni usano: finché li usano, non si tolgono. */
export function flowRuleAttributeIds(drafts: { skip?: SkipDraft; rework?: ReworkDraft }[]): string[] {
  return drafts.flatMap((task) => [task.skip?.rule, task.rework?.rule])
    .flatMap((groups) => (groups ?? []).flat().map((rule) => rule.attributeId));
}

/** Bozze lette dal localStorage: ciò che non torna si scarta, non rompe il pannello. */
export function sanitizeSkip(raw: unknown): SkipDraft | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const { percent, rule } = raw as SkipDraft;
  if (typeof percent !== "number") return undefined;
  return { percent, ...(isRuleGroups(rule) ? { rule } : {}) };
}

export function sanitizeRework(raw: unknown): ReworkDraft | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const { backTo, percent, maxRepeats, rule } = raw as ReworkDraft;
  if (typeof backTo !== "string" || typeof percent !== "number" || typeof maxRepeats !== "number") return undefined;
  return { backTo, percent, maxRepeats, ...(isRuleGroups(rule) ? { rule } : {}) };
}
