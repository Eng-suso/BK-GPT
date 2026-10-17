import type { CaseAttributeDraft } from "./caseRules";

/**
 * SIM-13b: un obiettivo di servizio per gruppo di casi ("premium entro 24
 * ore"). Il gruppo e' una categoria di un attributo del caso; `attributeId`
 * punta alla bozza dell'attributo, non al nome che puo' cambiare.
 */
export type SlaGoalDraft = { target: number; unit: "hours" | "days"; sharePercent: number };
export type SlaSegmentDraft = SlaGoalDraft & { attributeId: string; value: string };
export type SlaGoalIssue = "target" | "share";
export type SlaSegmentIssue = SlaGoalIssue | "attribute" | "duplicate";

export const MAX_SLA_SEGMENTS = 20;

export function goalSeconds(goal: SlaGoalDraft): number {
  return Math.round(goal.target * (goal.unit === "days" ? 86_400 : 3600));
}

export function goalIssue(goal: SlaGoalDraft): SlaGoalIssue | null {
  // Sui secondi inviati: un obiettivo che arrotondato vale zero non e' un obiettivo.
  if (!(Number.isFinite(goal.target) && goalSeconds(goal) >= 1)) return "target";
  if (!(Number.isFinite(goal.sharePercent) && goal.sharePercent > 0 && goal.sharePercent <= 100)) return "share";
  return null;
}

/** Le categorie a cui si puo' dare un obiettivo: solo attributi a categorie, con un nome. */
export function segmentAttributes(attributes: CaseAttributeDraft[]): Extract<CaseAttributeDraft, { kind: "category" }>[] {
  return attributes.filter((a): a is Extract<CaseAttributeDraft, { kind: "category" }> =>
    a.kind === "category" && a.name.trim() !== "" && a.categories.some((c) => c.value.trim()));
}

export function slaSegmentIssues(segments: SlaSegmentDraft[], attributes: CaseAttributeDraft[]): (SlaSegmentIssue | null)[] {
  const usable = segmentAttributes(attributes);
  const seen = new Set<string>();
  return segments.map((segment) => {
    const attribute = usable.find((a) => a.id === segment.attributeId);
    if (!attribute || !attribute.categories.some((c) => c.value.trim() === segment.value)) return "attribute";
    const key = `${segment.attributeId}\u0000${segment.value}`;
    if (seen.has(key)) return "duplicate";
    seen.add(key);
    return goalIssue(segment);
  });
}

/** Il prossimo gruppo da proporre: la prima categoria che non ha ancora un obiettivo. */
export function newSlaSegment(attributes: CaseAttributeDraft[], segments: SlaSegmentDraft[], goal: SlaGoalDraft): SlaSegmentDraft | null {
  for (const attribute of segmentAttributes(attributes)) {
    for (const category of attribute.categories) {
      const value = category.value.trim();
      if (value && !segments.some((s) => s.attributeId === attribute.id && s.value === value)) {
        return { attributeId: attribute.id, value, target: goal.target, unit: goal.unit, sharePercent: goal.sharePercent };
      }
    }
  }
  return null;
}

export function slaSegmentsInput(segments: SlaSegmentDraft[], attributes: CaseAttributeDraft[]) {
  return segments.flatMap((segment) => {
    const attribute = attributes.find((a) => a.id === segment.attributeId);
    // Il nome come lo riceve il motore (toModelPatch): e' quello che il log porta in colonna.
    return attribute ? [{
      attribute: attribute.name.trim(),
      value: segment.value,
      targetSeconds: goalSeconds(segment),
      share: segment.sharePercent / 100,
    }] : [];
  });
}

export function sanitizeSlaSegments(raw: unknown): SlaSegmentDraft[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
  const segments = raw.flatMap((item): SlaSegmentDraft[] => {
    if (!item || typeof item !== "object") return [];
    const value = item as Partial<SlaSegmentDraft>;
    if (typeof value.attributeId !== "string" || typeof value.value !== "string") return [];
    if (!finite(value.target) || !finite(value.sharePercent)) return [];
    return [{ attributeId: value.attributeId, value: value.value, target: value.target, sharePercent: value.sharePercent,
      unit: value.unit === "hours" ? "hours" : "days" }];
  }).slice(0, MAX_SLA_SEGMENTS);
  return segments.length ? segments : undefined;
}
