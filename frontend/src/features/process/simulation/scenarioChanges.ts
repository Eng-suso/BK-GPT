import type { ScenarioPatchOp, ScenarioPathStep } from "./scenarioPatch";

/**
 * SIM-14: una patch letta come una pull request ("Approvatore · Unità: 1 → 2").
 * Pura: le etichette arrivano dal chiamante (i18n), i nomi da AS-IS e template.
 */

export type ScenarioChange = {
  index: number;
  /** L'elemento del BPMN toccato, se e' un'attivita' o una decisione. */
  elementId: string | null;
  /** Cosa cambia: "Approvatore", il nome di un'attivita', "Scenario". */
  subject: string;
  /** Il campo, gia' tradotto; vuoto se cambia l'elemento intero. */
  field: string;
  kind: "changed" | "added" | "removed" | "reordered";
  from: string | null;
  to: string | null;
  /** L'operazione non si applica piu' all'AS-IS di oggi. */
  conflict: boolean;
};

export type ChangeLabels = {
  field: (key: string) => string;
  section: (key: string) => string;
  number: (value: number) => string;
  /** Un valore composto (un calendario, una regola): si dice solo che cambia. */
  complex: string;
  yes: string;
  no: string;
};

type Names = { elements: Record<string, string>; resources: Record<string, string> };

const ELEMENT_SECTIONS = new Set(["tasks", "gateways", "gatewayRules", "dismissedClaims"]);

function readPath(draft: unknown, path: ScenarioPathStep[]): unknown {
  let node = draft;
  for (const step of path) {
    if (typeof step === "object") {
      node = Array.isArray(node) ? node.find((item) => item && typeof item === "object" && (item as { id?: unknown }).id === step.id) : undefined;
    } else {
      node = node && typeof node === "object" && !Array.isArray(node) ? (node as Record<string, unknown>)[step] : undefined;
    }
    if (node === undefined) return undefined;
  }
  return node;
}

function format(value: unknown, key: string, labels: ChangeLabels, names: Names): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === "number") return labels.number(value);
  if (typeof value === "boolean") return value ? labels.yes : labels.no;
  if (typeof value === "string") return key === "resourceId" ? names.resources[value] ?? value : value;
  if (typeof value === "object" && value && "name" in value && typeof (value as { name: unknown }).name === "string") return (value as { name: string }).name;
  return labels.complex;
}

function itemName(section: string, step: { id: string }, baseline: unknown, value: unknown, names: Names): string {
  if (section === "resources" && names.resources[step.id]) return names.resources[step.id];
  for (const item of [readPath(baseline, [section, step]), value] as { name?: unknown }[]) {
    if (item && typeof item === "object" && typeof item.name === "string" && item.name) return item.name;
  }
  return step.id;
}

export function describeChanges(
  patch: ScenarioPatchOp[],
  conflicts: number[],
  baseline: unknown,
  names: Names,
  labels: ChangeLabels,
): ScenarioChange[] {
  return patch.map((op, index) => {
    const [section, second, ...rest] = op.path;
    const sectionKey = typeof section === "string" ? section : "";
    const elementId = ELEMENT_SECTIONS.has(sectionKey) && typeof second === "string" ? second : null;
    const value = op.op === "set" ? op.value : undefined;
    const subject = elementId
      ? names.elements[elementId] ?? elementId
      : typeof second === "object" && op.op !== "order"
        ? itemName(sectionKey, second, baseline, op.path.length === 2 ? value : undefined, names)
        : labels.section(sectionKey);
    // Il campo e' l'ultima chiave dopo il soggetto: "Unita'", "Durata media".
    const after = elementId || typeof second === "object" ? rest : op.path.slice(1);
    const fieldStep = [...after].reverse().find((step): step is string => typeof step === "string");
    const before = readPath(baseline, op.path);
    const kind: ScenarioChange["kind"] =
      op.op === "order" ? "reordered" : op.op === "remove" ? "removed" : before === undefined ? "added" : "changed";
    return {
      index,
      elementId,
      subject,
      field: fieldStep && op.op !== "order" ? labels.field(fieldStep) : "",
      kind,
      from: kind === "changed" ? format(before, fieldStep ?? sectionKey, labels, names) : null,
      to: op.op === "set" ? format(value, fieldStep ?? sectionKey, labels, names) : null,
      conflict: conflicts.includes(index),
    };
  });
}
