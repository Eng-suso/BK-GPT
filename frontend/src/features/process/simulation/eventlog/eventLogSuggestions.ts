import { emptyDraft, type MappingDraft } from "./eventLogMapping";

const aliases: Record<string, string[]> = {
  caseId: ["caseid", "case", "caseconceptname", "traceid", "processinstanceid", "processid", "idcaso", "idpratica", "idordine", "ordine", "pratica"],
  activity: ["activity", "activityname", "conceptname", "eventname", "task", "taskname", "attivita", "nomeattivita", "fase", "azione"],
  start: ["start", "starttime", "starttimestamp", "startedat", "inizio", "datainizio", "orainizio"],
  end: ["end", "endtime", "endtimestamp", "completedat", "completiontime", "fine", "datafine", "orafine", "completamento"],
  timestamp: ["timestamp", "timetimestamp", "eventtime", "datetime", "dataora", "dataevento"],
  lifecycle: ["lifecycle", "lifecycletransition", "transition", "statoevento"],
  resource: ["resource", "orgresource", "user", "utente", "operatore", "esecutore"],
  role: ["role", "orgrole", "ruolo"],
  cost: ["cost", "amount", "costo", "importo"],
  enable: ["enable", "enabletime", "enabledat", "abilitazione"],
};

const normalized = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");

export function suggestColumns(columns: string[]): MappingDraft {
  const draft = emptyDraft();
  const find = (field: keyof typeof aliases) => {
    const matches = columns.filter((column) => aliases[field].includes(normalized(column)));
    return matches.length === 1 ? matches[0] : "";
  };
  draft.caseId = find("caseId") ? [find("caseId")] : [];
  draft.activity = find("activity") ? [find("activity")] : [];
  draft.start = find("start");
  draft.end = find("end");
  draft.enable = find("enable");
  draft.timestamp = find("timestamp");
  draft.lifecycle = find("lifecycle");
  draft.resource = find("resource");
  draft.role = find("role");
  draft.cost = find("cost");
  if (!draft.end && draft.timestamp) draft.timeShape = "transition";
  return draft;
}

export const DATE_FORMATS = [
  { value: "", sample: "2026-11-23T14:30:00 (ISO 8601)" },
  { value: "%d/%m/%Y %H:%M:%S", sample: "23/11/2026 14:30:00" },
  { value: "%d/%m/%Y %H:%M", sample: "23/11/2026 14:30" },
  { value: "%Y-%m-%d %H:%M:%S", sample: "2026-11-23 14:30:00" },
  { value: "%Y-%m-%d %H:%M", sample: "2026-11-23 14:30" },
  { value: "%m/%d/%Y %H:%M:%S", sample: "11/23/2026 14:30:00" },
  { value: "%m/%d/%Y %H:%M", sample: "11/23/2026 14:30" },
  { value: "%d/%m/%Y", sample: "23/11/2026" },
  { value: "%Y-%m-%d", sample: "2026-11-23" },
  { value: "%m/%d/%Y", sample: "11/23/2026" },
] as const;

export function detectDateFormat(values: string[]): { pattern: string; ambiguous: boolean } {
  const samples = values.map((value) => value.trim()).filter(Boolean).slice(0, 20);
  if (!samples.length) return { pattern: "", ambiguous: false };
  if (samples.every((value) => /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/.test(value))) {
    return { pattern: "", ambiguous: false };
  }
  const slash = samples.map((value) => /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value));
  if (slash.every(Boolean)) {
    const dayFirst = slash.some((match) => Number(match![1]) > 12);
    const monthFirst = slash.some((match) => Number(match![2]) > 12);
    if (dayFirst && monthFirst) return { pattern: "", ambiguous: true };
    if (!dayFirst && !monthFirst) return { pattern: "", ambiguous: true };
    const date = dayFirst ? "%d/%m/%Y" : "%m/%d/%Y";
    const time = slash.some((match) => match![4]) ? (slash.some((match) => match![6]) ? " %H:%M:%S" : " %H:%M") : "";
    return { pattern: date + time, ambiguous: false };
  }
  return { pattern: "", ambiguous: true };
}

export function detectNumberFormat(values: string[]): { decimal: "." | ","; thousands: "" | "." | "," | " " | "'" } | null {
  const samples = values.map((value) => value.trim()).filter(Boolean).filter((value) => /^[-+]?\d[\d., '\s]*$/.test(value)).slice(0, 20);
  if (!samples.length) return null;
  const both = samples.find((value) => value.includes(",") && value.includes("."));
  if (both) return both.lastIndexOf(",") > both.lastIndexOf(".") ? { decimal: ",", thousands: "." } : { decimal: ".", thousands: "," };
  const commaDecimal = samples.some((value) => /,\d{1,2}$/.test(value));
  const decimal = commaDecimal ? "," : ".";
  const thousands = samples.some((value) => /\d \d{3}/.test(value)) ? " " : samples.some((value) => /\d'\d{3}/.test(value)) ? "'" : commaDecimal && samples.some((value) => /\d\.\d{3}/.test(value)) ? "." : decimal === "." && samples.some((value) => /\d,\d{3}/.test(value)) ? "," : "";
  return { decimal, thousands };
}
