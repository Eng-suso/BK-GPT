import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { API_BASE } from "@/lib/api";
import {
  chatScopeKey,
  toApiChatScope,
  type ChatScope,
} from "../../../contracts/chat";
import type { ChatSession } from "../types";
import { sessionTitle } from "../lib/normalizeSession";
import {
  chatKeys,
  clearChatSessions,
  createChatSession,
  deleteChatSession,
  fetchChatSession,
  fetchChatSessions,
} from "../api";

/** Backoff identical to the old manual retry loop, capped at 4s. */
const retryDelay = (attempt: number) => Math.min(1000 + attempt * 250, 4000);

export type UseChatSessions = {
  scopeKey: string;
  sessions: ChatSession[];
  activeSession: ChatSession | null;
  currentThreadId: string | null;
  isOffline: boolean;
  offlineMessage: string | null;
  selectThread: (threadId: string) => void;
  startNewThread: () => void;
  /** Return the active session, creating a backend session first if needed. */
  ensureThread: (firstMessage: string) => Promise<ChatSession>;
  deleteSession: (threadId: string) => Promise<void>;
  clearHistory: () => Promise<void>;
  /**
   * Write a finished transcript into the cache, then reconcile with the server.
   * The optimistic write stays even if the background refetch fails, so a
   * just-sent message can never disappear.
   */
  commitTranscript: (
    threadId: string,
    messages: ChatSession["messages"],
  ) => Promise<void>;
  retrySessions: () => void;
};

type Selection = {
  scopeKey: string;
  threadId: string | null;
  /** Whether the newest-thread auto-pick has already run for this scope. */
  autoPicked: boolean;
};

export function useChatSessions(
  scope: ChatScope,
  selectedModel: string,
): UseChatSessions {
  const queryClient = useQueryClient();
  const scopeKey = chatScopeKey(toApiChatScope(scope));

  const [selection, setSelection] = useState<Selection>({
    scopeKey,
    threadId: null,
    autoPicked: false,
  });

  const sessionsQuery = useQuery({
    queryKey: chatKeys.sessions(scopeKey),
    queryFn: () => fetchChatSessions(scopeKey),
    retry: 20,
    retryDelay,
  });

  // Reset on scope change, then pick the newest thread once that scope's list
  // arrives — both resolved during render (no effect), so a stale scope's
  // response can never overwrite the new scope's selection.
  const pendingScopeChange = selection.scopeKey !== scopeKey;
  if (pendingScopeChange) {
    setSelection({ scopeKey, threadId: null, autoPicked: false });
  }
  const firstThreadId = sessionsQuery.data?.[0]?.threadId ?? null;
  const shouldAutoPick =
    !pendingScopeChange &&
    !selection.autoPicked &&
    !selection.threadId &&
    Boolean(firstThreadId);
  if (shouldAutoPick) {
    setSelection({ scopeKey, threadId: firstThreadId, autoPicked: true });
  }
  const currentThreadId = pendingScopeChange
    ? null
    : shouldAutoPick
      ? firstThreadId
      : selection.threadId;

  const setThread = (threadId: string | null) => {
    setSelection({ scopeKey, threadId, autoPicked: true });
  };

  const detailQuery = useQuery({
    queryKey: chatKeys.session(currentThreadId ?? "none"),
    queryFn: () => fetchChatSession(currentThreadId as string),
    enabled: Boolean(currentThreadId),
  });

  const sessions = sessionsQuery.data ?? [];

  const listSession =
    sessions.find((s) => s.threadId === currentThreadId) ?? null;
  const activeSession =
    detailQuery.data && detailQuery.data.threadId === currentThreadId
      ? detailQuery.data
      : listSession;

  const isOffline =
    sessionsQuery.isError ||
    (sessionsQuery.isLoading && sessionsQuery.failureCount > 0);
  const offlineMessage = isOffline
    ? `Backend non raggiungibile su ${API_BASE || "origine corrente"}. Riprovo a caricare la cronologia...`
    : null;

  const ensureThread = async (firstMessage: string): Promise<ChatSession> => {
    const cached = queryClient
      .getQueryData<ChatSession[]>(chatKeys.sessions(scopeKey))
      ?.find((s) => s.threadId === currentThreadId);
    if (cached) return cached;
    const detail = currentThreadId
      ? queryClient.getQueryData<ChatSession>(chatKeys.session(currentThreadId))
      : undefined;
    if (detail && detail.threadId === currentThreadId) return detail;

    const created = await createChatSession({
      modelName: selectedModel,
      scope: toApiChatScope(scope, { includeTransient: false }),
    });
    const seeded: ChatSession = {
      ...created,
      title: sessionTitle(firstMessage),
      messages: [],
    };
    queryClient.setQueryData<ChatSession[]>(
      chatKeys.sessions(scopeKey),
      (prev) => [seeded, ...(prev ?? [])],
    );
    queryClient.setQueryData<ChatSession>(
      chatKeys.session(seeded.threadId),
      seeded,
    );
    setThread(seeded.threadId);
    return seeded;
  };

  const deleteSession = async (threadId: string) => {
    try {
      await deleteChatSession(threadId);
    } catch (err) {
      console.error("[chat] delete session failed", err);
    }
    queryClient.setQueryData<ChatSession[]>(
      chatKeys.sessions(scopeKey),
      (prev) => (prev ?? []).filter((s) => s.threadId !== threadId),
    );
    if (currentThreadId === threadId) setThread(null);
  };

  const clearHistory = async () => {
    try {
      await clearChatSessions(scopeKey);
    } catch (err) {
      console.error("[chat] clear history failed", err);
    }
    queryClient.setQueryData<ChatSession[]>(chatKeys.sessions(scopeKey), []);
    setThread(null);
  };

  const commitTranscript = async (
    threadId: string,
    messages: ChatSession["messages"],
  ) => {
    queryClient.setQueryData<ChatSession>(
      chatKeys.session(threadId),
      (prev) => ({
        threadId,
        title:
          prev?.title ??
          sessionTitle(
            messages.find((m) => m.role === "user")?.content ?? "",
          ),
        modelName: prev?.modelName ?? selectedModel,
        createdAt: prev?.createdAt,
        updatedAt: new Date().toISOString(),
        messageCount: messages.length,
        messages,
      }),
    );
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: chatKeys.session(threadId) }),
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(scopeKey) }),
    ]);
  };

  return {
    scopeKey,
    sessions,
    activeSession,
    currentThreadId,
    isOffline,
    offlineMessage,
    selectThread: (threadId: string) => setThread(threadId),
    startNewThread: () => setThread(null),
    ensureThread,
    deleteSession,
    clearHistory,
    commitTranscript,
    retrySessions: () => void sessionsQuery.refetch(),
  };
}
