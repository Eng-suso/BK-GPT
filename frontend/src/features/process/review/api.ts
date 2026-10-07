import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "@/lib/http";
import { onWorkspaceChanged } from "@/lib/workspaceEvents";
import { useEffect } from "react";
import { reviewActionSchema, reviewStateSchema, type CreateReviewAction } from "./reviewModel";

const key = (processId: string) => ["workspace", "impact-review", processId] as const;
export function useImpactReview(processId: string, bpmnModelId: string) {
  const client = useQueryClient();
  useEffect(() => onWorkspaceChanged(detail => {
    if (!detail.bpmnModelId || detail.bpmnModelId === bpmnModelId) void client.invalidateQueries({ queryKey: key(processId) });
  }), [processId, bpmnModelId, client]);
  return useQuery({ queryKey: key(processId), queryFn: async () => reviewStateSchema.parse(await http<unknown>(`/v1/workspace/processes/${processId}/impact-review`, { cache: "no-store" })) });
}
export function useCreateReviewAction(processId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateReviewAction) => reviewActionSchema.parse(await http<unknown>(`/v1/workspace/processes/${processId}/impact-review/actions`, { method: "POST", body: input })),
    onSuccess: () => client.invalidateQueries({ queryKey: key(processId) }),
  });
}
