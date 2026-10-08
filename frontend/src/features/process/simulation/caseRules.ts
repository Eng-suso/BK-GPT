/**
 * A2-1: attributi del caso e rami per regola nel pannello scenario.
 *
 * I campi della richiesta v1 non li esprimono: arrivano al backend come
 * `model_patch`, una ModelPatch dell'IR (backend/simulation/ir/patch.py)
 * applicata al modello tradotto dalla richiesta. Qui stanno la bozza che il
 * consulente modifica, cosa le manca per partire e la sua traduzione nella patch.
 */

export type CategoryDraft = { value: string; percent: number };

export type CaseAttributeDraft =
  | { id: string; name: string; kind: "category"; categories: CategoryDraft[] }
  | { id: string; name: string; kind: "number"; minimum: number; maximum: number };

export const CATEGORY_OPERATORS = ["=", "!="] as const;
export const NUMBER_OPERATORS = [">", ">=", "<", "<=", "=", "!="] as const;
export type RuleOperator = (typeof NUMBER_OPERATORS)[number];

/** Una condizione: `attributeId` punta alla bozza dell'attributo, non al nome che puo' cambiare. */
export type RuleDraft = { attributeId: string; operator: RuleOperator; value: string };
/** Vera se almeno un gruppo e' vero; un gruppo e' vero se tutte le sue condizioni lo sono. */
export type BranchRuleDraft = RuleDraft[][];
/** flow_id -> gruppi di condizioni. Presente = la decisione instrada per regola. */
export type GatewayRulesDraft = Record<string, BranchRuleDraft>;

/** Un numero come lo scrive il consulente: segno facoltativo, virgola o punto decimale. */
const NUMBER = /^-?\d+(?:[.,]\d+)?$/;

export type AttributeIssue = "name" | "duplicateName" | "categories" | "categoryValue" | "categorySum" | "bounds";
export type RuleIssue = "missingRule" | "incompleteRule" | "unknownAttribute" | "notANumber";

const PROVENANCE = { origin: "manual" } as const;

export function newAttributeId(existing: CaseAttributeDraft[]): string {
  let n = existing.length + 1;
  while (existing.some((a) => a.id === `attr-${n}`)) n += 1;
  return `attr-${n}`;
}

export function categorySum(attribute: Extract<CaseAttributeDraft, { kind: "category" }>): number {
  return attribute.categories.reduce((total, c) => total + (Number.isFinite(c.percent) ? c.percent : 0), 0);
}

export function attributeIssue(attribute: CaseAttributeDraft, all: CaseAttributeDraft[]): AttributeIssue | null {
  const name = attribute.name.trim();
  if (!name) return "name";
  if (all.some((other) => other.id !== attribute.id && other.name.trim() === name)) return "duplicateName";
  if (attribute.kind === "number") {
    return Number.isFinite(attribute.minimum) && Number.isFinite(attribute.maximum) && attribute.minimum < attribute.maximum ? null : "bounds";
  }
  if (attribute.categories.length === 0) return "categories";
  const values = attribute.categories.map((c) => c.value.trim());
  if (values.some((v) => !v) || new Set(values).size !== values.length) return "categoryValue";
  if (attribute.categories.some((c) => !(c.percent > 0))) return "categorySum";
  return Math.abs(categorySum(attribute) - 100) < 0.5 ? null : "categorySum";
}

/** I gruppi di una regola su un attributo numerico accettano solo numeri. */
export function operatorsFor(attribute: CaseAttributeDraft | undefined): readonly RuleOperator[] {
  return attribute?.kind === "category" ? CATEGORY_OPERATORS : NUMBER_OPERATORS;
}

export function ruleIssue(groups: BranchRuleDraft | undefined, attributes: CaseAttributeDraft[]): RuleIssue | null {
  const rules = (groups ?? []).flat();
  if (rules.length === 0) return "missingRule";
  for (const rule of rules) {
    const attribute = attributes.find((a) => a.id === rule.attributeId);
    if (!attribute) return "unknownAttribute";
    if (!rule.value.trim()) return "incompleteRule";
    if (!operatorsFor(attribute).includes(rule.operator)) return "incompleteRule";
    if (attribute.kind === "number" && !NUMBER.test(rule.value.trim())) return "notANumber";
  }
  return null;
}

/** Quante decisioni per regola e quanti attributi impediscono il run. */
export function caseRuleIssues(attributes: CaseAttributeDraft[], gatewayRules: Record<string, GatewayRulesDraft>) {
  const badAttributes = attributes.filter((a) => attributeIssue(a, attributes) !== null).length;
  const badGateways = Object.values(gatewayRules).filter((branches) =>
    Object.values(branches).some((groups) => ruleIssue(groups, attributes) !== null)).length;
  return { attributes: badAttributes, gateways: badGateways, ready: badAttributes === 0 && badGateways === 0 };
}

/** La prima condizione di una regola nuova: il primo attributo con il suo primo valore. */
export function defaultRule(attributes: CaseAttributeDraft[]): RuleDraft {
  const attribute = attributes[0];
  if (attribute?.kind === "category") return { attributeId: attribute.id, operator: "=", value: attribute.categories[0]?.value ?? "" };
  return { attributeId: attribute?.id ?? "", operator: ">", value: "" };
}

/** Una regola si legge come una frase: "importo > 5000 e tipo = premium, oppure …". */
export function ruleSentence(groups: BranchRuleDraft, attributes: CaseAttributeDraft[], words: { and: string; or: string }): string {
  return groups
    .map((group) => group.map((rule) => `${attributes.find((a) => a.id === rule.attributeId)?.name.trim() || "?"} ${rule.operator} ${rule.value}`).join(` ${words.and} `))
    .join(`, ${words.or} `);
}

type IrDistribution = { kind: "uniform"; minimum: number; maximum: number };
export type ModelPatchInput = {
  case_attributes?: Array<
    | { name: string; options: { value: string; probability: number }[]; provenance: typeof PROVENANCE }
    | { name: string; distribution: IrDistribution; provenance: typeof PROVENANCE }
  >;
  gateways?: Array<{
    element_id: string;
    branches: Array<{
      flow_id: string;
      probability: number;
      condition: { any_of: Array<Array<{ attribute: string; operator: RuleOperator; value: string | number }>> };
      provenance: typeof PROVENANCE;
    }>;
  }>;
};

/**
 * La patch IR della bozza, o `undefined` se non c'e' nulla che la v1 non sappia
 * gia' dire. Le decisioni per regola sostituiscono quelle a percentuale.
 */
export function toModelPatch(
  attributes: CaseAttributeDraft[],
  gatewayRules: Record<string, GatewayRulesDraft>,
): ModelPatchInput | undefined {
  if (attributes.length === 0) return undefined;
  const byId = new Map(attributes.map((a) => [a.id, a]));
  const caseAttributes: NonNullable<ModelPatchInput["case_attributes"]> = attributes.map((attribute) => {
    if (attribute.kind === "number") {
      return { name: attribute.name.trim(), distribution: { kind: "uniform", minimum: attribute.minimum, maximum: attribute.maximum }, provenance: PROVENANCE };
    }
    // Pesi normalizzati: 33,3 + 33,3 + 33,4 non deve diventare 0,9999 per il backend.
    const total = categorySum(attribute) || 1;
    return {
      name: attribute.name.trim(),
      options: attribute.categories.map((c) => ({ value: c.value.trim(), probability: c.percent / total })),
      provenance: PROVENANCE,
    };
  });
  const gateways = Object.entries(gatewayRules).map(([elementId, branches]) => {
    const flows = Object.entries(branches);
    return {
      element_id: elementId,
      branches: flows.map(([flowId, groups]) => ({
        flow_id: flowId,
        // Ignorata dal motore quando ogni ramo ha una regola; l'IR la vuole fra 0 e 1.
        probability: 1 / flows.length,
        condition: {
          any_of: groups.map((group) => group.map((rule) => {
            const attribute = byId.get(rule.attributeId);
            const raw = rule.value.trim();
            return {
              attribute: attribute?.name.trim() ?? rule.attributeId,
              operator: rule.operator,
              value: attribute?.kind === "number" ? Number(raw.replace(",", ".")) : raw,
            };
          })),
        },
        provenance: PROVENANCE,
      })),
    };
  });
  return { case_attributes: caseAttributes, ...(gateways.length ? { gateways } : {}) };
}

/** Bozze lette dal localStorage: cio' che non torna si scarta, non rompe il pannello. */
export function sanitizeAttributes(raw: unknown): CaseAttributeDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((a): a is CaseAttributeDraft => {
    if (!a || typeof a !== "object" || typeof a.id !== "string" || typeof a.name !== "string") return false;
    if (a.kind === "number") return typeof a.minimum === "number" && typeof a.maximum === "number";
    return a.kind === "category" && Array.isArray(a.categories) &&
      a.categories.every((c: unknown) => Boolean(c) && typeof (c as CategoryDraft).value === "string" && typeof (c as CategoryDraft).percent === "number");
  });
}

export function sanitizeGatewayRules(raw: unknown): Record<string, GatewayRulesDraft> {
  if (!raw || typeof raw !== "object") return {};
  const isRule = (r: unknown): r is RuleDraft => Boolean(r) && typeof (r as RuleDraft).attributeId === "string" &&
    typeof (r as RuleDraft).value === "string" && (NUMBER_OPERATORS as readonly string[]).includes((r as RuleDraft).operator);
  const out: Record<string, GatewayRulesDraft> = {};
  for (const [gateway, branches] of Object.entries(raw as Record<string, unknown>)) {
    if (!branches || typeof branches !== "object") continue;
    const clean: GatewayRulesDraft = {};
    for (const [flow, groups] of Object.entries(branches as Record<string, unknown>)) {
      if (Array.isArray(groups) && groups.every((g) => Array.isArray(g) && g.every(isRule))) clean[flow] = groups as BranchRuleDraft;
    }
    out[gateway] = clean;
  }
  return out;
}
