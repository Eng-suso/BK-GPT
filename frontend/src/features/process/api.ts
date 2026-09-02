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
import { http } from "@/lib/http";

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

export async function fetchBpmnVersions(
  bpmnModelId: string,
): Promise<BpmnVersion[]> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/versions`,
    { cache: "no-store" },
  );
  return apiBpmnVersionsSchema.parse(raw).map(toBpmnVersion);
}

export async function saveBpmnModelXml(
  bpmnModelId: string,
  xml: string,
): Promise<void> {
  await http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}`, {
    method: "PUT",
    body: { xml },
  });
}

/** Restore a stored version; returns the model the backend rewound to. */
export async function restoreBpmnVersion(
  bpmnModelId: string,
  versionId: number,
): Promise<BpmnModel> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/versions/${versionId}/restore`,
    { method: "POST" },
  );
  return toBpmnModel(apiRestoreBpmnVersionSchema.parse(raw).bpmn_model);
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
    queryFn: () => fetchBpmnVersions(bpmnModelId),
  });
}

export function useSaveBpmnModelMutation(bpmnModelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (xml: string) => saveBpmnModelXml(bpmnModelId, xml),
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
    mutationFn: (versionId: number) =>
      restoreBpmnVersion(bpmnModelId, versionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: bpmnKeys.scope(bpmnModelId),
      });
    },
  });
}
