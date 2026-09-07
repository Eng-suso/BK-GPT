import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { httpErrorMessage } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";
import {
  toApiChatAttachment,
  toApiChatScope,
  type ChatAttachment,
  type ChatMode,
  type ChatScope,
} from "../../../contracts/chat";
import type { ChatMessage, ChatSession } from "../types";
import { streamChatMessage } from "../api";
import {
  clearRun,
  dropQueuedMessage,
  enqueueMessage,
  getRun,
  getRunsVersion,
  startRun,
  stopRun,
  subscribeToRuns,
  type QueuedMessage,
} from "../stream/chatRunStore";

type UseChatStreamArgs = {
  scope: ChatScope;
  selectedModel: string;
  chatMode: ChatMode;
  activeSession: ChatSession | null;
  ensureThread: (firstMessage: string) => Promise<ChatSession>;
  selectThread: (threadId: string) => void;
  commitTranscript: (
    threadId: string,
    messages: ChatMessage[],
  ) => Promise<void>;
  /** Runs after a stream completes successfully (e.g. reload the BPMN review). */
  onSettled?: (threadId: string) => void;
};

export type UseChatStream = {
  isBusy: boolean;
  lastUserPrompt: string;
  lastUserAttachments: ChatAttachment[];
  liveThreadId: string | null;
  liveMessages: ChatMessage[] | null;
  /** Messaggi scritti durante il turno e non ancora inviati. */
  queuedMessages: QueuedMessage[];
  streamError: string | null;
  /** Da quando l'agente sta lavorando, per il cronometro. */
  startedAtMs: number | null;
  sendMessage: (
    content: string,
    attachments?: ChatAttachment[],
  ) => Promise<void>;
  /** Ferma il turno in corso tenendo la risposta parziale. */
  stopStreaming: () => void;
  cancelQueuedMessage: (index: number) => void;
  clearStreamError: () => void;
};

function notifyChatWorkspaceChanged(scope: ChatScope) {
  if (scope.type !== "canvas") {
    notifyWorkspaceChanged();
    return;
  }
  notifyWorkspaceChanged({
    bpmnModelId: scope.bpmnModelId,
    forceCanvasReload: true,
  });
}

/**
 * Espone il turno in corso su questo thread.
 *
 * Il turno non vive qui: vive nello store di modulo (`chatRunStore`), e questo
 * hook lo osserva. E' la ragione per cui cambiare pagina non lo interrompe piu'
 * — smontare il componente toglie solo l'osservatore.
 *
 * @param scope - Ambito di lavoro della conversazione
 * @param selectedModel - Modello usato per generare la risposta
 * @param chatMode - Modalita' di lavoro della richiesta
 * @param activeSession - Sessione attiva
 * @param ensureThread - Crea o recupera il thread del messaggio
 * @param selectThread - Seleziona un thread
 * @param commitTranscript - Consolida il trascritto finito
 * @param onSettled - Callback opzionale a turno riuscito
 * @returns Stato del turno e comandi per inviare, fermare e accodare
 */
export function useChatStream({
  scope,
  selectedModel,
  chatMode,
  activeSession,
  ensureThread,
  selectThread,
  commitTranscript,
  onSettled,
}: UseChatStreamArgs): UseChatStream {
  // Latest values for the async send flow without re-memoising `sendMessage`.
  const scopeRef = useRef(scope);
  const modelRef = useRef(selectedModel);
  const modeRef = useRef(chatMode);
  const activeSessionRef = useRef(activeSession);
  // Il thread appena aperto, prima che `activeSession` lo rispecchi. Vive in due
  // posti perche' serve a due tempi diversi: lo stato fa ridisegnare il turno
  // appena parte, il ref lo rende leggibile dentro il flusso async di invio
  // senza rimemoizzare `sendMessage`. Il solo ref non bastava: scriverlo non
  // ridisegna, quindi il turno restava invisibile fino al render successivo.
  const [liveThreadId, setLiveThreadId] = useState<string | null>(null);
  const liveThreadRef = useRef<string | null>(null);

  const trackLiveThread = useCallback((threadId: string) => {
    liveThreadRef.current = threadId;
    setLiveThreadId(threadId);
  }, []);
  useEffect(() => {
    scopeRef.current = scope;
    modelRef.current = selectedModel;
    modeRef.current = chatMode;
    activeSessionRef.current = activeSession;
  });

  useSyncExternalStore(subscribeToRuns, getRunsVersion, getRunsVersion);

  const activeThreadId = activeSession?.threadId ?? liveThreadId;
  const run = getRun(activeThreadId);

  const clearStreamError = useCallback(() => {
    if (activeThreadId) clearRun(activeThreadId);
  }, [activeThreadId]);

  const sendMessage = useCallback(
    async (content: string, attachments: ChatAttachment[] = []) => {
      const currentThreadId = activeSessionRef.current?.threadId ?? liveThreadRef.current;
      const currentRun = getRun(currentThreadId);

      // Un turno e' gia' in corso: il messaggio si accoda invece di sparire o di
      // scavalcare la risposta che il consulente sta ancora leggendo.
      if (currentRun?.status === "streaming" && currentThreadId) {
        enqueueMessage(currentThreadId, content, attachments);
        return;
      }

      let session: ChatSession;
      try {
        session = await ensureThread(content);
      } catch (err) {
        console.error("[chat] could not open a session", err);
        const detail = httpErrorMessage(err, "Errore sconosciuto");
        const fallbackId = `local-error-${Date.now()}`;
        trackLiveThread(fallbackId);
        selectThread(fallbackId);
        await startRun({
          threadId: fallbackId,
          base: [],
          content,
          attachments,
          transport: () => Promise.reject(new Error(detail)),
          commit: async () => {},
        });
        return;
      }

      const threadId = session.threadId;
      trackLiveThread(threadId);
      const existingRun = getRun(threadId);
      const base = (
        existingRun && existingRun.status !== "streaming"
          ? existingRun.messages
          : session.threadId === activeSessionRef.current?.threadId
            ? activeSessionRef.current.messages
            : session.messages
      ).filter((message) => message.role !== "error");

      const scopeAtSend = scopeRef.current;
      const modelAtSend = modelRef.current;
      const modeAtSend = modeRef.current;

      await startRun({
        threadId,
        base,
        content,
        attachments,
        transport: (id, input, signal) =>
          streamChatMessage(
            id,
            {
              message: input.message,
              modelName: modelAtSend,
              scope: toApiChatScope(scopeAtSend),
              mode: modeAtSend,
              attachments: input.attachments.map(toApiChatAttachment),
            },
            signal,
          ),
        commit: commitTranscript,
        onSettled: (id) => {
          notifyChatWorkspaceChanged(scopeAtSend);
          onSettled?.(id);
        },
      });
    },
    [ensureThread, selectThread, commitTranscript, onSettled, trackLiveThread],
  );

  const stopStreaming = useCallback(() => {
    if (activeThreadId) stopRun(activeThreadId);
  }, [activeThreadId]);

  const cancelQueuedMessage = useCallback(
    (index: number) => {
      if (activeThreadId) dropQueuedMessage(activeThreadId, index);
    },
    [activeThreadId],
  );

  return {
    isBusy: run?.status === "streaming",
    lastUserPrompt: run?.lastPrompt ?? "",
    lastUserAttachments: run?.lastAttachments ?? [],
    liveThreadId: run ? run.threadId : null,
    liveMessages: run ? run.messages : null,
    queuedMessages: run?.queued ?? [],
    streamError: run?.error ?? null,
    startedAtMs: run?.status === "streaming" ? run.startedAtMs : null,
    sendMessage,
    stopStreaming,
    cancelQueuedMessage,
    clearStreamError,
  };
}
