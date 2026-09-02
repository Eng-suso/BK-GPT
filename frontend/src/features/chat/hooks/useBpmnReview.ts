import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { httpErrorMessage } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";
import type { ChatScope } from "../../../contracts/chat";
import type { BpmnReview } from "../types";
import { approveBpmnReview, chatKeys, fetchBpmnReview } from "../api";

export type UseBpmnReview = {
  review: BpmnReview | null;
  isApproving: boolean;
  approve: () => void;
  reload: () => Promise<void>;
};

export function useBpmnReview(
  scope: ChatScope,
  onToast: (message: string) => void,
): UseBpmnReview {
  const queryClient = useQueryClient();
  const bpmnModelId = scope.type === "canvas" ? scope.bpmnModelId : null;
  const queryKey = chatKeys.review(bpmnModelId ?? "none");

  const reviewQuery = useQuery({
    queryKey,
    queryFn: () => fetchBpmnReview(bpmnModelId as string),
    enabled: Boolean(bpmnModelId),
  });

  const approveMutation = useMutation({
    mutationFn: () => approveBpmnReview(bpmnModelId as string),
    onSuccess: () => {
      queryClient.setQueryData<BpmnReview | null>(queryKey, null);
      if (bpmnModelId) {
        notifyWorkspaceChanged({
          bpmnModelId,
          forceCanvasReload: true,
        });
      }
      onToast("BPMN generato e salvato.");
    },
    onError: (err) => {
      onToast(
        httpErrorMessage(err, "Nessuna review BPMN pendente da approvare."),
      );
    },
  });

  const approve = useCallback(() => {
    if (!bpmnModelId || !reviewQuery.data) return;
    approveMutation.mutate();
  }, [bpmnModelId, reviewQuery.data, approveMutation]);

  const reload = useCallback(async () => {
    if (!bpmnModelId) return;
    await queryClient.invalidateQueries({ queryKey });
  }, [queryClient, bpmnModelId, queryKey]);

  return {
    review: reviewQuery.data ?? null,
    isApproving: approveMutation.isPending,
    approve,
    reload,
  };
}
