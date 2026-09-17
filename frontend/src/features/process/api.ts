import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  apiBpmnModelSchema,
  apiBpmnVersionsSchema,
  apiElementReviewSchema,
  apiProcessProvenanceSchema,
  apiRestoreBpmnVersionSchema,
  toBpmnModel,
  toBpmnVersion,
  toElementReviewResult,
  toProcessProvenance,
  type BpmnModel,
  type BpmnVersion,
  type ElementReviewDecision,
  type ElementReviewResult,
  type ProcessProvenance,
} from "@/contracts/workspace";
import { http } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";

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

export const provenanceKeys = {
  process: (processId: string) => ["workspace", "provenance", processId] as const,
};

export async function fetchProcessProvenance(
  processId: string,
): Promise<ProcessProvenance> {
  const raw = await http<unknown>(`/v1/workspace/processes/${processId}/provenance`, {
    cache: "no-store",
  });
  return toProcessProvenance(apiProcessProvenanceSchema.parse(raw));
}

export async function reviewProvenanceElement(
  processId: string,
  input: { sourceRef: string; decision: ElementReviewDecision; note?: string },
): Promise<ElementReviewResult> {
  const raw = await http<unknown>(
    `/v1/workspace/processes/${processId}/provenance/decisions`,
    {
      method: "POST",
      body: {
        source_ref: input.sourceRef,
        decision: input.decision,
        note: input.note ?? "",
      },
    },
  );
  return toElementReviewResult(apiElementReviewSchema.parse(raw));
}

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

export function useProcessProvenanceQuery(
  processId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<ProcessProvenance> {
  return useQuery({
    queryKey: provenanceKeys.process(processId),
    queryFn: () => fetchProcessProvenance(processId),
    enabled: options.enabled ?? true,
    staleTime: 0,
  });
}

/**
 * Conferma o rifiuto di un elemento del piano.
 *
 * Il backend rilegge tutto dopo la scrittura e restituisce il rapporto nuovo:
 * lo si mette direttamente in cache invece di rifare la richiesta. Il canvas si
 * ricarica dal backend - con un rifiuto anche sopra una bozza locale, perche' il
 * disegno e' stato rigenerato e la bozza descrive un piano che non esiste piu'.
 */
export function useReviewProvenanceElementMutation(processId: string, bpmnModelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { sourceRef: string; decision: ElementReviewDecision; note?: string }) =>
      reviewProvenanceElement(processId, input),
    onSuccess: (result, input) => {
      if (result.provenance) {
        queryClient.setQueryData(provenanceKeys.process(processId), result.provenance);
      } else {
        void queryClient.invalidateQueries({ queryKey: provenanceKeys.process(processId) });
      }
      void queryClient.invalidateQueries({ queryKey: bpmnKeys.scope(bpmnModelId) });
      notifyWorkspaceChanged({
        bpmnModelId,
        forceCanvasReload: input.decision === "rejected" && result.draftStatus === "drafted",
      });
    },
  });
}
