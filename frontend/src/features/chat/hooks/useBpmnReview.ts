import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { httpErrorMessage } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";
import type { ChatScope } from "../../../contracts/chat";
import type { BpmnReview, BpmnReviewVersion } from "../types";
import {
  answerBpmnReviewQuestion,
  approveBpmnReview,
  chatKeys,
  fetchBpmnReview,
  fetchBpmnReviewVersions,
  saveBpmnReview,
} from "../api";

export type UseBpmnReview = {
  review: BpmnReview | null;
  versions: BpmnReviewVersion[];
  isApproving: boolean;
  isSaving: boolean;
  isAnswering: boolean;
  approve: () => void;
  save: (bpmnBrief: string) => Promise<void>;
  answerQuestion: (question: string, answer: string) => Promise<void>;
  reload: () => Promise<void>;
};

/**
 * Manages loading and updating the BPMN review for a chat scope.
 *
 * @param scope - The chat scope used to identify the BPMN model.
 * @param onToast - Callback for displaying operation status messages.
 * @returns The current review, its version history, mutation states, and review actions.
 */
export function useBpmnReview(
  scope: ChatScope,
  onToast: (message: string) => void,
): UseBpmnReview {
  const queryClient = useQueryClient();
  // Il piano appartiene al processo, non alla scheda che lo mostra: la
  // discussione che raccoglie le evidenze e il canvas che le disegna leggono lo
  // stesso modello.
  const bpmnModelId =
    scope.type === "canvas"
      ? scope.bpmnModelId
      : scope.type === "process"
        ? scope.bpmnModelId ?? null
        : null;
  const queryKey = chatKeys.review(bpmnModelId ?? "none");

  const reviewQuery = useQuery({
    queryKey,
    queryFn: () => fetchBpmnReview(bpmnModelId as string),
    enabled: Boolean(bpmnModelId),
  });

  const versionsQuery = useQuery({
    queryKey: chatKeys.reviewVersions(bpmnModelId ?? "none"),
    queryFn: () => fetchBpmnReviewVersions(bpmnModelId as string),
    enabled: Boolean(bpmnModelId),
  });

  const answerMutation = useMutation({
    mutationFn: (input: { question: string; answer: string }) =>
      answerBpmnReviewQuestion(bpmnModelId as string, input),
    onSuccess: (updated) => {
      queryClient.setQueryData<BpmnReview>(queryKey, updated);
      // Answering writes a new version: the history on screen must not lag it.
      void queryClient.invalidateQueries({
        queryKey: chatKeys.reviewVersions(bpmnModelId ?? "none"),
      });
      onToast("Risposta registrata nel piano.");
    },
    onError: (err) => {
      onToast(httpErrorMessage(err, "Non è stato possibile registrare la risposta."));
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveBpmnReview(bpmnModelId as string),
    onSuccess: () => {
      queryClient.setQueryData<BpmnReview | null>(queryKey, null);
      void queryClient.invalidateQueries({
        queryKey: chatKeys.reviewVersions(bpmnModelId ?? "none"),
      });
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

  const saveMutation = useMutation({
    mutationFn: (bpmnBrief: string) =>
      saveBpmnReview(bpmnModelId as string, bpmnBrief),
    onSuccess: (savedReview) => {
      queryClient.setQueryData<BpmnReview>(queryKey, savedReview);
      onToast("Piano Markdown salvato.");
    },
    onError: (err) => {
      onToast(httpErrorMessage(err, "Non è stato possibile salvare il piano."));
    },
  });

  const approve = useCallback(() => {
    if (!bpmnModelId || !reviewQuery.data) return;
    approveMutation.mutate();
  }, [bpmnModelId, reviewQuery.data, approveMutation]);

  const save = useCallback(
    async (bpmnBrief: string) => {
      if (!bpmnModelId || !reviewQuery.data) return;
      await saveMutation.mutateAsync(bpmnBrief);
    },
    [bpmnModelId, reviewQuery.data, saveMutation],
  );

  const answerQuestion = useCallback(
    async (question: string, answer: string) => {
      if (!bpmnModelId) return;
      await answerMutation.mutateAsync({ question, answer });
    },
    [bpmnModelId, answerMutation],
  );

  const reload = useCallback(async () => {
    if (!bpmnModelId) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey }),
      queryClient.invalidateQueries({
        queryKey: chatKeys.reviewVersions(bpmnModelId),
      }),
    ]);
  }, [queryClient, bpmnModelId, queryKey]);

  return {
    review: reviewQuery.data ?? null,
    versions: versionsQuery.data ?? [],
    isApproving: approveMutation.isPending,
    isSaving: saveMutation.isPending,
    isAnswering: answerMutation.isPending,
    approve,
    save,
    answerQuestion,
    reload,
  };
}
