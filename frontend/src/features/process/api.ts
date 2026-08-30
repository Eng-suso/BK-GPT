import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  apiBpmnModelSchema,
  apiBpmnVersionsSchema,
  apiRestoreBpmnVersionSchema,
  toBpmnModel,
  toBpmnVersion,
  type BpmnModel,
  type BpmnVersion,
} from "@/contracts/workspace";
import { HttpError, http } from "@/lib/http";

/**
 * Query/mutation hooks for the process BPMN model. Components never call
 * `fetch` — see docs/frontend-stack.md (`lib/api.ts` = single backend seam,
 * TanStack Query owns server state, no `workspace:refresh` bus).
 */

export const bpmnKeys = {
  all: ["workspace", "bpmn"] as const,
  scope: (bpmnModelId: string) => [...bpmnKeys.all, bpmnModelId] as const,
  model: (bpmnModelId: string) => [...bpmnKeys.all, bpmnModelId, "model"] as const,
  versions: (bpmnModelId: string) =>
    [...bpmnKeys.all, bpmnModelId, "versions"] as const,
};

export async function fetchBpmnModel(bpmnModelId: string): Promise<BpmnModel> {
  const raw = await http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}`, {
    cache: "no-store",
  });
  return toBpmnModel(apiBpmnModelSchema.parse(raw));
}

export function useBpmnModelQuery(
  bpmnModelId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<BpmnModel> {
  return useQuery({
    queryKey: bpmnKeys.model(bpmnModelId),
    queryFn: () => fetchBpmnModel(bpmnModelId),
    enabled: options.enabled ?? true,
    staleTime: 0,
  });
}

export function useBpmnVersionsQuery(
  bpmnModelId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<BpmnVersion[]> {
  return useQuery({
    queryKey: bpmnKeys.versions(bpmnModelId),
    enabled: options.enabled ?? true,
    queryFn: async () => {
      const raw = await http<unknown>(
        `/v1/workspace/bpmn-models/${bpmnModelId}/versions`,
        { cache: "no-store" },
      );
      return apiBpmnVersionsSchema.parse(raw).map(toBpmnVersion);
    },
  });
}

export function useSaveBpmnModelMutation(bpmnModelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (xml: string) =>
      http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}`, {
        method: "PUT",
        body: { xml },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: bpmnKeys.scope(bpmnModelId),
      });
    },
  });
}

export function useRestoreBpmnVersionMutation(bpmnModelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (versionId: number) => {
      const raw = await http<unknown>(
        `/v1/workspace/bpmn-models/${bpmnModelId}/versions/${versionId}/restore`,
        { method: "POST" },
      );
      return apiRestoreBpmnVersionSchema.parse(raw);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: bpmnKeys.scope(bpmnModelId),
      });
    },
  });
}

/** Human-readable message from a backend error (`{detail}` / `{error:{message}}`). */
export function bpmnErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof HttpError) {
    const body = error.body;
    if (body && typeof body === "object") {
      if ("detail" in body && typeof body.detail === "string") {
        return body.detail;
      }
      const nested = (body as { error?: { message?: unknown } }).error;
      if (nested && typeof nested.message === "string") {
        return nested.message;
      }
    }
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}
