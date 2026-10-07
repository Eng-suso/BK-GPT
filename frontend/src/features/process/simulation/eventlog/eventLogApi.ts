import { http } from "@/lib/http";

import {
  eventLogAnalysisSchema,
  eventLogListSchema,
  eventLogPreviewSchema,
  eventLogTemplateListSchema,
  eventLogTemplateSchema,
  uploadedEventLogSchema,
  type ApplyMappingInput,
  type ColumnMapping,
  type Delimiter,
  type EventLog,
  type EventLogAnalysis,
  type EventLogPreview,
  type EventLogTemplate,
  type UploadedEventLog,
} from "./eventLogTypes";

const BASE = "/v1/workspace";

export function eventLogUploadForm(file: File, delimiter?: Delimiter): FormData {
  const body = new FormData();
  body.append("file", file);
  if (delimiter) body.append("delimiter", delimiter);
  return body;
}

export async function uploadEventLog(processId: string, file: File, delimiter?: Delimiter): Promise<UploadedEventLog> {
  const raw = await http<unknown>(`${BASE}/processes/${encodeURIComponent(processId)}/event-logs`, {
    method: "POST",
    body: eventLogUploadForm(file, delimiter),
  });
  return uploadedEventLogSchema.parse(raw);
}

export async function fetchEventLogs(processId: string): Promise<EventLog[]> {
  const raw = await http<unknown>(`${BASE}/processes/${encodeURIComponent(processId)}/event-logs`);
  return eventLogListSchema.parse(raw);
}

export async function fetchEventLogPreview(eventLogId: string, delimiter?: Delimiter): Promise<EventLogPreview> {
  const query = delimiter ? `?delimiter=${encodeURIComponent(delimiter)}` : "";
  const raw = await http<unknown>(`${BASE}/event-logs/${encodeURIComponent(eventLogId)}/preview${query}`);
  return eventLogPreviewSchema.parse(raw);
}

export async function applyEventLogMapping(eventLogId: string, input: ApplyMappingInput): Promise<EventLogAnalysis> {
  const raw = await http<unknown>(`${BASE}/event-logs/${encodeURIComponent(eventLogId)}/mapping`, {
    method: "POST",
    body: {
      mapping: input.mapping,
      template_id: input.templateId,
      delimiter: input.delimiter,
      activity_matches: input.activityMatches,
      resource_matches: input.resourceMatches,
    },
  });
  return eventLogAnalysisSchema.parse(raw);
}

export async function fetchEventLogAnalysis(eventLogId: string): Promise<EventLogAnalysis> {
  const raw = await http<unknown>(`${BASE}/event-logs/${encodeURIComponent(eventLogId)}/analysis`);
  return eventLogAnalysisSchema.parse(raw);
}

export async function deleteEventLog(eventLogId: string): Promise<void> {
  await http<unknown>(`${BASE}/event-logs/${encodeURIComponent(eventLogId)}`, { method: "DELETE" });
}

export async function fetchEventLogTemplates(): Promise<EventLogTemplate[]> {
  const raw = await http<unknown>(`${BASE}/event-log-templates`);
  return eventLogTemplateListSchema.parse(raw);
}

export async function saveEventLogTemplate(input: {
  name: string;
  mapping: ColumnMapping;
  columns: string[];
  templateKey?: string;
}): Promise<EventLogTemplate> {
  const raw = await http<unknown>(`${BASE}/event-log-templates`, {
    method: "POST",
    body: { name: input.name, mapping: input.mapping, columns: input.columns, template_key: input.templateKey },
  });
  return eventLogTemplateSchema.parse(raw);
}
