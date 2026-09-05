import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { httpErrorMessage } from "@/lib/http";
import { notifyWorkspaceChanged } from "@/lib/workspaceEvents";
import { toApiChatScope, type ChatScope } from "../../../contracts/chat";
import type { ChatMessage, ChatSession } from "../types";
import {
  completeAgentActivity,
  nextAgentActivity,
} from "../lib/agentActivity";
import { streamChatMessage } from "../api";

type LiveTranscript = { threadId: string; messages: ChatMessage[] };

type UseChatStreamArgs = {
  scope: ChatScope;
  selectedModel: string;
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
  liveThreadId: string | null;
  liveMessages: ChatMessage[] | null;
  streamError: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearStreamError: () => void;
};

function replaceThinkingWithError(
  messages: ChatMessage[],
  thinkingLabel: string,
  errorText: string,
): ChatMessage[] {
  const last = messages.at(-1);
  const isPendingAssistant =
    last?.role === "assistant" &&
    (last.content === thinkingLabel || !last.content?.trim());
  const trimmed = isPendingAssistant ? messages.slice(0, -1) : messages;
  return [...trimmed, { role: "error", content: errorText }];
}

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

export function useChatStream({
  scope,
  selectedModel,
  activeSession,
  ensureThread,
  selectThread,
  commitTranscript,
  onSettled,
}: UseChatStreamArgs): UseChatStream {
  const { t } = useTranslation("chat");

  const [isBusy, setIsBusy] = useState(false);
  const [lastUserPrompt, setLastUserPrompt] = useState("");
  const [live, setLive] = useState<LiveTranscript | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Latest values for the async send flow without re-memoising `sendMessage`.
  const scopeRef = useRef(scope);
  const modelRef = useRef(selectedModel);
  const activeSessionRef = useRef(activeSession);
  useEffect(() => {
    scopeRef.current = scope;
    modelRef.current = selectedModel;
    activeSessionRef.current = activeSession;
  });

  const clearStreamError = useCallback(() => setStreamError(null), []);

  const sendMessage = useCallback(
    async (content: string) => {
      const thinkingLabel = t("status.thinking");
      setLastUserPrompt(content);
      setStreamError(null);
      setIsBusy(true);

      const userMessage: ChatMessage = { role: "user", content };
      const thinkingMessage: ChatMessage = {
        role: "assistant",
        content: "",
        activity: [],
      };

      let threadId: string;
      let base: ChatMessage[];
      try {
        const session = await ensureThread(content);
        threadId = session.threadId;
        base = (
          session.threadId === activeSessionRef.current?.threadId
            ? activeSessionRef.current.messages
            : session.messages
        ).filter((m) => m.role !== "error");
      } catch (err) {
        console.error("[chat] could not open a session", err);
        const detail = httpErrorMessage(err, "Errore sconosciuto");
        const fallbackId = `local-error-${Date.now()}`;
        selectThread(fallbackId);
        setLive({
          threadId: fallbackId,
          messages: [
            userMessage,
            {
              role: "error",
              content: `Non sono riuscito a completare questa richiesta. ${detail}`,
            },
          ],
        });
        setIsBusy(false);
        return;
      }

      let localMessages: ChatMessage[] = [...base, userMessage, thinkingMessage];
      setLive({ threadId, messages: localMessages });

      const updateLive = (
        updater: (messages: ChatMessage[]) => ChatMessage[],
      ) => {
        localMessages = updater(localMessages);
        setLive((prev) =>
          prev && prev.threadId === threadId
            ? { ...prev, messages: localMessages }
            : prev,
        );
      };

      try {
        const res = await streamChatMessage(threadId, {
          message: content,
          modelName: modelRef.current,
          scope: toApiChatScope(scopeRef.current),
        });
        if (!res.body) throw new Error("Streaming fallito");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let accumulatedText = "";
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            const event = JSON.parse(line);

            if (event.type === "activity") {
              const label = String(event.message || event.content || "").trim();
              const key = String(
                event.payload?.activity_id ||
                  `${event.node || "agent"}:${label || Date.now()}`,
              );
              updateLive((messages) => {
                const next = [...messages];
                const last = next[next.length - 1];
                if (!last || last.role !== "assistant") return messages;
                next[next.length - 1] = {
                  ...last,
                  activity: nextAgentActivity(
                    last.activity,
                    key,
                    label,
                    typeof event.payload?.icon === "string"
                      ? event.payload.icon
                      : undefined,
                  ),
                };
                return next;
              });
            }

            if (event.type === "delta") {
              accumulatedText += event.content || "";
              updateLive((messages) => {
                const next = [...messages];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...(last || { role: "assistant" as const }),
                  role: "assistant",
                  content: accumulatedText,
                };
                return next;
              });
            }

            if (event.type === "done") {
              accumulatedText = event.message || accumulatedText;
              updateLive((messages) => {
                const next = [...messages];
                const last = next[next.length - 1];
                if (!last || last.role !== "assistant") return messages;
                next[next.length - 1] = {
                  ...last,
                  role: "assistant",
                  content: accumulatedText,
                  activity: completeAgentActivity(last.activity),
                };
                return next;
              });
            }

            if (event.type === "error") {
              throw new Error(
                event.error?.detail ||
                  event.error?.message ||
                  event.detail ||
                  "Errore backend",
              );
            }
          }
        }

        await commitTranscript(threadId, localMessages);
        notifyChatWorkspaceChanged(scopeRef.current);
        onSettled?.(threadId);
        setLive((prev) => (prev?.threadId === threadId ? null : prev));
      } catch (err) {
        console.error("[chat] stream failed", err);
        const detail = httpErrorMessage(err, "Errore sconosciuto");
        setStreamError(
          `Backend non raggiungibile o richiesta fallita: ${detail}`,
        );
        updateLive((messages) =>
          replaceThinkingWithError(
            messages,
            thinkingLabel,
            `Non sono riuscito a completare questa richiesta. ${detail}`,
          ),
        );
      } finally {
        setIsBusy(false);
      }
    },
    [t, ensureThread, selectThread, commitTranscript, onSettled],
  );

  return {
    isBusy,
    lastUserPrompt,
    liveThreadId: live?.threadId ?? null,
    liveMessages: live?.messages ?? null,
    streamError,
    sendMessage,
    clearStreamError,
  };
}
