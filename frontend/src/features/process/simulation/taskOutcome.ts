/**
 * SIM-31b: l'esito di un'attività nel pannello scenario.
 *
 * Finita l'attività, il caso riceve un esito: una categoria scelta con la sua
 * percentuale ("Verifica: OK 80%, KO 20%"). È un attributo dell'attività, non
 * del caso: all'arrivo non c'è, perché il motore non lascia un'attività
 * cambiare un attributo del caso. Le decisioni, i salti e le rilavorazioni a
 * valle lo leggono nelle loro regole come un attributo a categorie; per un
 * caso che non è passato dall'attività una regola sull'esito non è mai vera.
 *
 * Arriva al backend con la config del task (`outcome`), che lo scrive nell'IR
 * prima della `model_patch` (backend/simulation/ir/from_request.py).
 */
import { categorySum, type CaseAttributeDraft, type CategoryDraft } from "./caseRules";

export type OutcomeDraft = { name: string; categories: CategoryDraft[] };

export type OutcomeIssue = "name" | "duplicateName" | "reservedName" | "categories" | "categoryValue" | "categorySum";

export type OutcomeInput = { attribute: string; options: { value: string; probability: number }[] };

/** Le regole puntano a un attributo per id: quello di un esito è legato all'attività. */
const OUTCOME_PREFIX = "outcome:";

export function outcomeAttributeId(elementId: string): string {
  return `${OUTCOME_PREFIX}${elementId}`;
}

export function isOutcomeAttributeId(id: string): boolean {
  return id.startsWith(OUTCOME_PREFIX);
}

/** L'esito appena acceso: due categorie, da rinominare. */
export function defaultOutcome(): OutcomeDraft {
  return { name: "esito", categories: [{ value: "OK", percent: 80 }, { value: "KO", percent: 20 }] };
}

/**
 * Gli esiti come attributi a categorie, per gli editor delle regole. Si
 * aggiungono agli attributi del caso solo dove le regole li possono leggere:
 * decisioni, salti e rilavorazioni.
 */
export function outcomeAttributes(tasks: Record<string, { outcome?: OutcomeDraft }>): CaseAttributeDraft[] {
  return Object.entries(tasks).flatMap(([elementId, task]) => task.outcome
    ? [{ id: outcomeAttributeId(elementId), name: task.outcome.name, kind: "category" as const, categories: task.outcome.categories }]
    : []);
}

/**
 * Cosa manca all'esito per partire. `elementId` è la sua attività; il nome
 * non può essere quello di un attributo del caso né di un altro esito.
 */
export function outcomeIssue(
  elementId: string,
  outcome: OutcomeDraft,
  attributes: CaseAttributeDraft[],
  outcomes: CaseAttributeDraft[],
): OutcomeIssue | null {
  const name = outcome.name.trim();
  if (!name) return "name";
  // Il backend riserva i nomi dei contatori delle rilavorazioni.
  if (name.startsWith("delir_")) return "reservedName";
  const taken = [...attributes, ...outcomes.filter((o) => o.id !== outcomeAttributeId(elementId))];
  if (taken.some((other) => other.name.trim() === name)) return "duplicateName";
  if (outcome.categories.length === 0) return "categories";
  const values = outcome.categories.map((c) => c.value.trim());
  if (values.some((v) => !v) || new Set(values).size !== values.length) return "categoryValue";
  if (outcome.categories.some((c) => !(c.percent > 0))) return "categorySum";
  return Math.abs(outcomeSum(outcome) - 100) < 0.5 ? null : "categorySum";
}

export function outcomeSum(outcome: OutcomeDraft): number {
  return categorySum({ id: "", name: outcome.name, kind: "category", categories: outcome.categories });
}

export function outcomeInput(outcome: OutcomeDraft): OutcomeInput {
  // Pesi normalizzati come per gli attributi del caso: 33,3 × 3 non deve arrivare come 0,999.
  const total = outcomeSum(outcome) || 1;
  return {
    attribute: outcome.name.trim(),
    options: outcome.categories.map((c) => ({ value: c.value.trim(), probability: c.percent / total })),
  };
}

/** Bozze lette dal localStorage: ciò che non torna si scarta, non rompe il pannello. */
export function sanitizeOutcome(raw: unknown): OutcomeDraft | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const { name, categories } = raw as OutcomeDraft;
  if (typeof name !== "string" || !Array.isArray(categories)) return undefined;
  const valid = categories.every((c: unknown) => Boolean(c) && typeof (c as CategoryDraft).value === "string" &&
    typeof (c as CategoryDraft).percent === "number");
  return valid ? { name, categories } : undefined;
}
