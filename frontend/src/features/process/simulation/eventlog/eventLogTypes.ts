import { z } from "zod";

/**
 * Contratto delle API di import degli event log (SIM-15).
 * Backend: backend/schemas/eventlog.py. I nomi restano quelli del backend
 * (snake_case): il mapping viaggia avanti e indietro identico.
 */

export const DELIMITERS = [",", ";", "\t", "|"] as const;
export type Delimiter = (typeof DELIMITERS)[number];

export const ATTRIBUTE_TYPES = ["text", "number", "category", "date"] as const;
export type AttributeType = (typeof ATTRIBUTE_TYPES)[number];

const attributeColumnSchema = z.object({
  column: z.string(),
  name: z.string(),
  type: z.enum(ATTRIBUTE_TYPES),
});

export const columnMappingSchema = z.object({
  case_id: z.array(z.string()).min(1),
  activity: z.array(z.string()).min(1),
  start: z.string().nullable().optional(),
  end: z.string().nullable().optional(),
  enable: z.string().nullable().optional(),
  timestamp: z.string().nullable().optional(),
  lifecycle: z.string().nullable().optional(),
  resource: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  cost: z.string().nullable().optional(),
  case_attributes: z.array(attributeColumnSchema).default([]),
  event_attributes: z.array(attributeColumnSchema).default([]),
  timestamps: z.object({ pattern: z.string().nullable().optional(), timezone: z.string() }),
  numbers: z.object({ decimal: z.enum([".", ","]), thousands: z.enum(["", ".", ",", " ", "'"]) }),
  joiner: z.string().optional(),
});
export type ColumnMapping = z.infer<typeof columnMappingSchema>;
export type AttributeColumn = z.infer<typeof attributeColumnSchema>;

const templateRefSchema = z.object({
  id: z.number(),
  template_key: z.string(),
  version: z.number(),
  name: z.string(),
});

export const eventLogSchema = z.object({
  id: z.string(),
  process_id: z.string(),
  name: z.string(),
  format: z.enum(["csv", "xes"]),
  delimiter: z.string().nullable(),
  byte_size: z.number(),
  row_count: z.number(),
  columns: z.array(z.string()),
  status: z.enum(["uploaded", "mapped"]),
  mapping: columnMappingSchema.nullable(),
  template: templateRefSchema.nullable(),
  created_at: z.string(),
  mapped_at: z.string().nullable(),
});
export type EventLog = z.infer<typeof eventLogSchema>;
export const eventLogListSchema = z.array(eventLogSchema);

export const eventLogPreviewSchema = z.object({
  format: z.enum(["csv", "xes"]),
  delimiter: z.string().nullable(),
  columns: z.array(z.string()),
  row_count: z.number(),
  sample_rows: z.array(z.array(z.string())),
});
export type EventLogPreview = z.infer<typeof eventLogPreviewSchema>;

export const uploadedEventLogSchema = eventLogSchema.extend({
  created: z.boolean(),
  preview: eventLogPreviewSchema,
});
export type UploadedEventLog = z.infer<typeof uploadedEventLogSchema>;

const matchReason = z.enum(["same_name", "ambiguous", "none"]);

export const qualityReportSchema = z.object({
  rows_read: z.number(),
  rows_excluded: z.number(),
  events: z.number(),
  cases: z.number(),
  activities: z.number(),
  resources: z.number(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  events_without_start: z.number(),
  issues: z.array(z.object({
    code: z.string(),
    message: z.string(),
    count: z.number(),
    rows: z.array(z.number()),
    excludes_rows: z.boolean(),
  })),
});
export type QualityReport = z.infer<typeof qualityReportSchema>;

export const activityReportSchema = z.object({
  bpmn_version_id: z.number().nullable(),
  confirmed: z.boolean(),
  matches: z.array(z.object({
    activity: z.string(),
    events: z.number(),
    element_id: z.string().nullable(),
    reason: matchReason,
  })),
  unmatched_activities: z.array(z.string()),
  unobserved_elements: z.array(z.object({ element_id: z.string(), name: z.string() })),
});
export type ActivityReport = z.infer<typeof activityReportSchema>;

export const resourceReportSchema = z.object({
  confirmed: z.boolean(),
  matches: z.array(z.object({
    resource: z.string(),
    events: z.number(),
    model_resource_id: z.string().nullable(),
    reason: matchReason,
  })),
  unmatched_resources: z.array(z.string()),
  unobserved_model_resources: z.array(z.object({ resource_id: z.string(), name: z.string() })),
  events_without_resource: z.number(),
});
export type ResourceReport = z.infer<typeof resourceReportSchema>;

/**
 * I KPI del log reale: lo stesso calcolo dei run simulati, ma un log reale puo'
 * non sapere il costo (`cost: null`) ne' l'inizio delle attivita' (`timing`).
 */
/** B3.2: secondi di attesa per causa, sulle esecuzioni con l'abilitazione osservabile. */
export const waitingCauseSchema = z.enum(["contention", "unavailability", "extraneous", "batching"]);
export type WaitingCause = z.infer<typeof waitingCauseSchema>;

const waitingCausesSchema = z.object({
  activities: z.array(
    z.object({
      name: z.string(),
      el: z.string().nullable(),
      executions: z.number(),
      waiting: z.number(),
      seconds: z.record(waitingCauseSchema, z.number()),
    }),
  ),
});

export const eventLogSummarySchema = z
  .object({
    casesCompleted: z.number(),
    cycle: z.object({ avg: z.number(), p50: z.number(), p90: z.number() }).loose(),
    waiting: z.object({ avg: z.number() }).loose(),
    processing: z.object({ avg: z.number() }).loose(),
    throughputPerHour: z.number(),
    cost: z.object({ total: z.number(), perCase: z.number().nullable() }).loose().nullable(),
    timing: z.enum(["start_and_end", "complete_only", "mixed"]),
    firstEnableObserved: z.boolean().optional(),
    enablementObserved: z.boolean().optional(),
    /** null: il log non ha inizio e persona su quasi tutti gli eventi; assente nei log importati prima di B3.2. */
    waitingCauses: waitingCausesSchema.nullable().optional(),
  })
  .loose();
export type EventLogSummary = z.infer<typeof eventLogSummarySchema>;

export const eventLogAnalysisSchema = z.object({
  event_log: eventLogSchema,
  quality: qualityReportSchema,
  activities: activityReportSchema,
  resources: resourceReportSchema,
  summary: eventLogSummarySchema.nullable(),
});
export type EventLogAnalysis = z.infer<typeof eventLogAnalysisSchema>;

export const eventLogTemplateSchema = z.object({
  id: z.number(),
  template_key: z.string(),
  version: z.number(),
  name: z.string(),
  mapping: columnMappingSchema,
  columns: z.array(z.string()),
  created_at: z.string(),
});
export type EventLogTemplate = z.infer<typeof eventLogTemplateSchema>;
export const eventLogTemplateListSchema = z.array(eventLogTemplateSchema);

export type ApplyMappingInput = {
  mapping?: ColumnMapping;
  templateId?: number;
  delimiter?: Delimiter;
  activityMatches?: Record<string, string | null>;
  resourceMatches?: Record<string, string | null>;
};

/** Token replay dei casi reali sul BPMN (backend: EventLogConformanceResponse). */
export const conformanceSchema = z.object({
  event_log: eventLogSchema,
  bpmn_version_id: z.number().nullable(),
  mapping_bpmn_version_id: z.number().nullable(),
  fitness: z.number(),
  cases: z.number(),
  fitting_cases: z.number(),
  fitting_share: z.number(),
  deviations: z.array(z.object({
    element_id: z.string(),
    name: z.string(),
    executed_out_of_order: z.number(),
    left_waiting: z.number(),
    cases_affected: z.number(),
  })),
  variants: z.array(z.object({
    activities: z.array(z.string()),
    cases: z.number(),
    fitness: z.number(),
    fits: z.boolean(),
    out_of_order: z.array(z.string()),
    waiting: z.array(z.string()),
    unmodeled: z.array(z.string()),
  })),
  unmodeled_activities: z.record(z.string(), z.number()),
  unobserved_elements: z.array(z.object({ element_id: z.string(), name: z.string() })),
  excluded_variants: z.number(),
  excluded_cases: z.number(),
  warnings: z.array(z.object({ code: z.string(), params: z.record(z.string(), z.union([z.string(), z.number()])) })),
});
export type Conformance = z.infer<typeof conformanceSchema>;
