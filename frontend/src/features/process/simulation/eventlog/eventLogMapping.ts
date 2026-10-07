import type { AttributeColumn, AttributeType, ColumnMapping } from "./eventLogTypes";

/**
 * La bozza del mapping che il wizard modifica, e la sua traduzione nel
 * `ColumnMapping` del backend. Nessuna colonna viene indovinata dal nome: le
 * sceglie il consulente, o le porta un template salvato.
 */

export type TimeShape = "interval" | "transition";
export type Thousands = ColumnMapping["numbers"]["thousands"];

export type MappingDraft = {
  caseId: string[];
  activity: string[];
  timeShape: TimeShape;
  start: string;
  end: string;
  timestamp: string;
  lifecycle: string;
  resource: string;
  role: string;
  cost: string;
  caseAttributes: AttributeColumn[];
  eventAttributes: AttributeColumn[];
  pattern: string;
  timezone: string;
  decimal: "." | ",";
  thousands: Thousands;
};

export type DraftIssue = "caseId" | "activity" | "end" | "timestamp" | "attributeName" | "attributeNameDuplicate";

export const DEFAULT_TIMEZONE = "Europe/Rome";

export function emptyDraft(): MappingDraft {
  return {
    caseId: [],
    activity: [],
    timeShape: "interval",
    start: "",
    end: "",
    timestamp: "",
    lifecycle: "",
    resource: "",
    role: "",
    cost: "",
    caseAttributes: [],
    eventAttributes: [],
    pattern: "",
    timezone: DEFAULT_TIMEZONE,
    decimal: ".",
    thousands: "",
  };
}

export function draftFromMapping(mapping: ColumnMapping): MappingDraft {
  const transition = Boolean(mapping.timestamp);
  return {
    caseId: [...mapping.case_id],
    activity: [...mapping.activity],
    timeShape: transition ? "transition" : "interval",
    start: mapping.start ?? "",
    end: mapping.end ?? "",
    timestamp: mapping.timestamp ?? "",
    lifecycle: mapping.lifecycle ?? "",
    resource: mapping.resource ?? "",
    role: mapping.role ?? "",
    cost: mapping.cost ?? "",
    caseAttributes: mapping.case_attributes.map((a) => ({ ...a })),
    eventAttributes: mapping.event_attributes.map((a) => ({ ...a })),
    pattern: mapping.timestamps.pattern ?? "",
    timezone: mapping.timestamps.timezone,
    decimal: mapping.numbers.decimal,
    thousands: mapping.numbers.thousands,
  };
}

const orNull = (value: string): string | null => (value.trim() ? value : null);

export function toColumnMapping(draft: MappingDraft): ColumnMapping {
  const interval = draft.timeShape === "interval";
  return {
    case_id: draft.caseId,
    activity: draft.activity,
    start: interval ? orNull(draft.start) : null,
    end: interval ? orNull(draft.end) : null,
    timestamp: interval ? null : orNull(draft.timestamp),
    lifecycle: interval ? null : orNull(draft.lifecycle),
    resource: orNull(draft.resource),
    role: orNull(draft.role),
    cost: orNull(draft.cost),
    case_attributes: draft.caseAttributes,
    event_attributes: draft.eventAttributes,
    timestamps: { pattern: orNull(draft.pattern), timezone: draft.timezone || DEFAULT_TIMEZONE },
    numbers: { decimal: draft.decimal, thousands: draft.thousands },
  };
}

/** Cio' che manca perche' il backend accetti il mapping, nell'ordine del wizard. */
export function draftIssues(draft: MappingDraft): DraftIssue[] {
  const issues: DraftIssue[] = [];
  if (draft.caseId.length === 0) issues.push("caseId");
  if (draft.activity.length === 0) issues.push("activity");
  if (draft.timeShape === "interval" && !draft.end) issues.push("end");
  if (draft.timeShape === "transition" && !draft.timestamp) issues.push("timestamp");
  const attributes = [...draft.caseAttributes, ...draft.eventAttributes];
  if (attributes.some((a) => !a.name.trim())) issues.push("attributeName");
  const names = attributes.map((a) => a.name.trim()).filter(Boolean);
  if (new Set(names).size !== names.length) issues.push("attributeNameDuplicate");
  return issues;
}

/** Le colonne che il mapping usa: per segnalarle nell'anteprima. */
export function usedColumns(draft: MappingDraft): Set<string> {
  const mapping = toColumnMapping(draft);
  const single = [mapping.start, mapping.end, mapping.timestamp, mapping.lifecycle, mapping.resource, mapping.role, mapping.cost];
  return new Set([
    ...mapping.case_id,
    ...mapping.activity,
    ...single.filter((value): value is string => Boolean(value)),
    ...mapping.case_attributes.map((a) => a.column),
    ...mapping.event_attributes.map((a) => a.column),
  ]);
}

/** Le colonne di un template che il file non ha: il template non si applica. */
export function missingTemplateColumns(mapping: ColumnMapping, fileColumns: string[]): string[] {
  const used = usedColumns(draftFromMapping(mapping));
  const available = new Set(fileColumns);
  return [...used].filter((column) => !available.has(column)).sort();
}

export function addAttribute(list: AttributeColumn[], column: string, type: AttributeType = "text"): AttributeColumn[] {
  return [...list, { column, name: column, type }];
}

/** Abbinamento corrente (attivita' o risorsa -> elemento), dal report del backend. */
export function matchesFrom<T extends { element_id?: string | null; model_resource_id?: string | null }>(
  rows: T[],
  key: (row: T) => string,
): Record<string, string | null> {
  return Object.fromEntries(rows.map((row) => [key(row), row.element_id ?? row.model_resource_id ?? null]));
}
