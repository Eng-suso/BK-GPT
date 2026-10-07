import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  applyEventLogMapping,
  deleteEventLog,
  fetchEventLogAnalysis,
  fetchEventLogPreview,
  fetchEventLogs,
  fetchEventLogTemplates,
  saveEventLogTemplate,
  uploadEventLog,
} from "./eventLogApi";
import type { ApplyMappingInput, ColumnMapping, Delimiter } from "./eventLogTypes";

export const eventLogKeys = {
  list: (processId: string) => ["workspace", "event-logs", processId] as const,
  preview: (eventLogId: string, delimiter: Delimiter | null) => ["workspace", "event-log-preview", eventLogId, delimiter] as const,
  analysis: (eventLogId: string) => ["workspace", "event-log-analysis", eventLogId] as const,
  templates: ["workspace", "event-log-templates"] as const,
};

export function useEventLogs(processId: string) {
  return useQuery({ queryKey: eventLogKeys.list(processId), queryFn: () => fetchEventLogs(processId) });
}

export function useEventLogPreview(eventLogId: string | null, delimiter: Delimiter | null) {
  return useQuery({
    queryKey: eventLogKeys.preview(eventLogId ?? "", delimiter),
    queryFn: () => fetchEventLogPreview(eventLogId!, delimiter ?? undefined),
    enabled: Boolean(eventLogId),
  });
}

export function useEventLogAnalysis(eventLogId: string | null, mapped: boolean) {
  return useQuery({
    queryKey: eventLogKeys.analysis(eventLogId ?? ""),
    queryFn: () => fetchEventLogAnalysis(eventLogId!),
    enabled: Boolean(eventLogId) && mapped,
  });
}

export function useEventLogTemplates() {
  return useQuery({ queryKey: eventLogKeys.templates, queryFn: fetchEventLogTemplates });
}

export function useUploadEventLog(processId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, delimiter }: { file: File; delimiter?: Delimiter }) => uploadEventLog(processId, file, delimiter),
    onSuccess: () => client.invalidateQueries({ queryKey: eventLogKeys.list(processId) }),
  });
}

export function useApplyEventLogMapping(processId: string, eventLogId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ApplyMappingInput) => applyEventLogMapping(eventLogId!, input),
    onSuccess: (analysis) => {
      client.setQueryData(eventLogKeys.analysis(analysis.event_log.id), analysis);
      void client.invalidateQueries({ queryKey: eventLogKeys.list(processId) });
    },
  });
}

export function useDeleteEventLog(processId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (eventLogId: string) => deleteEventLog(eventLogId),
    onSuccess: () => client.invalidateQueries({ queryKey: eventLogKeys.list(processId) }),
  });
}

export function useSaveEventLogTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; mapping: ColumnMapping; columns: string[]; templateKey?: string }) =>
      saveEventLogTemplate(input),
    onSuccess: () => client.invalidateQueries({ queryKey: eventLogKeys.templates }),
  });
}
