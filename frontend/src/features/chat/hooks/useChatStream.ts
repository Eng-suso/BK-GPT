import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { httpErrorMessage } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";
import {
  chatScopeKey,
  toApiChatAttachment,
  toApiChatScope,
  type ChatAttachment,
  type ChatScope,
  type ChatTurnChoices,
} from "../../../contracts/chat";
import type { ChatMessage, ChatSession } from "../types";
import { streamChatMessage } from "../api";
import {
  clearRunError,
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
  /** Postura e autonomia scelte dal consulente per il prossimo turno. */
  choices: ChatTurnChoices;
  activeSession: ChatSession | null;
  currentThreadId: string | null;
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
  /** La postura con cui DeliR ha letto l'ultima richiesta, se l'ha scelta lui. */
  detectedPosture: string | null;
  sendMessage: (
    content: string,
    attachments?: ChatAttachment[],
    choicesOverride?: Partial<ChatTurnChoices>,
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
    forceCanvasReload: !scope.reviewNodeId,
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
 * @param choices - Postura e autonomia del turno
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
  choices,
  activeSession,
  currentThreadId,
  ensureThread,
  selectThread,
  commitTranscript,
  onSettled,
}: UseChatStreamArgs): UseChatStream {
  // Latest values for the async send flow without re-memoising `sendMessage`.
  const scopeRef = useRef(scope);
  const modelRef = useRef(selectedModel);
  const choicesRef = useRef(choices);
  const activeSessionRef = useRef(activeSession);
  const currentThreadRef = useRef(currentThreadId);
  const scopeKey = chatScopeKey(toApiChatScope(scope));
  const openingRef = useRef<string | null>(null);
  const openingInput = useRef<string | null>(null);
  const pendingOpeningRef = useRef<{ scopeKey: string; messages: QueuedMessage[] } | null>(null);
  const [pendingOpening, setPendingOpening] = useState<{ scopeKey: string; messages: QueuedMessage[] } | null>(null);
  const openingGeneration = useRef(0);
  const [openingScope, setOpeningScope] = useState<string | null>(null);
  useEffect(() => {
    scopeRef.current = scope;
    modelRef.current = selectedModel;
    choicesRef.current = choices;
    activeSessionRef.current = activeSession;
    currentThreadRef.current = currentThreadId;
  });

  useSyncExternalStore(subscribeToRuns, getRunsVersion, getRunsVersion);

  const activeThreadId = currentThreadId;
  const run = getRun(activeThreadId);

  const clearStreamError = useCallback(() => {
    if (activeThreadId) clearRunError(activeThreadId);
  }, [activeThreadId]);

  const sendMessage = useCallback(
    async (
      content: string,
      attachments: ChatAttachment[] = [],
      choicesOverride?: Partial<ChatTurnChoices>,
    ) => {
      const scopeAtSend = scopeRef.current;
      const keyAtSend = chatScopeKey(toApiChatScope(scopeAtSend));
      const modelAtSend = modelRef.current;
      const choicesAtSend = { ...choicesRef.current, ...choicesOverride };
      if (openingRef.current === keyAtSend) {
        if (content === openingInput.current && !attachments.length) return;
        const pending = pendingOpeningRef.current;
        const next = { scopeKey: keyAtSend, messages: [...(pending?.scopeKey === keyAtSend ? pending.messages : []), { content, attachments }] };
        pendingOpeningRef.current = next; setPendingOpening(next);
        return;
      }
      const currentThreadId = currentThreadRef.current;
      const currentRun = getRun(currentThreadId);

      // Un turno e' gia' in corso: il messaggio si accoda invece di sparire o di
      // scavalcare la risposta che il consulente sta ancora leggendo.
      if (currentRun?.status === "streaming" && currentThreadId) {
        enqueueMessage(currentThreadId, content, attachments);
        return;
      }

      openingRef.current = keyAtSend;
      openingInput.current = content;
      const generation = ++openingGeneration.current;
      setOpeningScope(keyAtSend);
      let session: ChatSession;
      try {
        session = await ensureThread(content);
        if (openingGeneration.current !== generation) return;
      } catch (err) {
        if (openingGeneration.current !== generation) return;
        console.error("[chat] could not open a session", err);
        const detail = httpErrorMessage(err, "Errore sconosciuto");
        const fallbackId = `local-error-${Date.now()}`;

        if (chatScopeKey(toApiChatScope(scopeRef.current)) === keyAtSend) selectThread(fallbackId);
        await startRun({
          threadId: fallbackId,
          base: [],
          content,
          attachments,
          transport: () => Promise.reject(new Error(detail)),
          commit: async () => {},
        });
        return;
      } finally {
        if (openingGeneration.current === generation) { openingRef.current = null; setOpeningScope(null); }
      }

      const threadId = session.threadId;

      const existingRun = getRun(threadId);
      let base = (
        existingRun && existingRun.status !== "streaming"
          ? existingRun.messages
          : session.threadId === activeSessionRef.current?.threadId
            ? activeSessionRef.current.messages
            : session.messages
      ).filter((message) => message.role !== "error");
      // A retry of an empty failed turn replaces its pending user bubble.
      if (existingRun?.status === "error" && base.at(-1)?.role === "user" && base.at(-1)?.content === content) base = base.slice(0, -1);

      const runPromise = startRun({
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
              choices: choicesAtSend,
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
      const pending = pendingOpeningRef.current;
      if (pending?.scopeKey === keyAtSend) {
        for (const message of pending.messages) enqueueMessage(threadId, message.content, message.attachments);
        pendingOpeningRef.current = null; setPendingOpening(null);
      }
      await runPromise;
    },
    [ensureThread, selectThread, commitTranscript, onSettled],
  );

  const stopStreaming = useCallback(() => {
    if (openingRef.current) { openingGeneration.current += 1; openingRef.current = null; pendingOpeningRef.current = null; setPendingOpening(null); setOpeningScope(null); }
    if (activeThreadId) stopRun(activeThreadId);
  }, [activeThreadId]);

  const cancelQueuedMessage = useCallback(
    (index: number) => {
      if (pendingOpeningRef.current?.scopeKey === scopeKey) {
        const next = { scopeKey, messages: pendingOpeningRef.current.messages.filter((_, i) => i !== index) };
        pendingOpeningRef.current = next; setPendingOpening(next); return;
      }
      if (activeThreadId) dropQueuedMessage(activeThreadId, index);
    },
    [activeThreadId, scopeKey],
  );

  return {
    isBusy: openingScope === scopeKey || run?.status === "streaming",
    lastUserPrompt: run?.lastPrompt ?? "",
    lastUserAttachments: run?.lastAttachments ?? [],
    liveThreadId: run ? run.threadId : null,
    liveMessages: run ? run.messages : null,
    queuedMessages: pendingOpening?.scopeKey === scopeKey ? pendingOpening.messages : run?.queued ?? [],
    streamError: run?.error ?? null,
    startedAtMs: run?.status === "streaming" ? run.startedAtMs : null,
    detectedPosture: run?.detectedPosture ?? null,
    sendMessage,
    stopStreaming,
    cancelQueuedMessage,
    clearStreamError,
  };
}
