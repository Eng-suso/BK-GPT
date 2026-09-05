import React, { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE } from "@/lib/api";
import type { ChatScope } from "./chatScope";
import { titleForScope } from "./chatScope";
import { ChatShell } from "./ChatShell";
import { transcribeAudio } from "./api";
import { useBpmnReview } from "./hooks/useBpmnReview";
import { useChatSessions } from "./hooks/useChatSessions";
import { useChatStream } from "./hooks/useChatStream";
import { BpmnReviewCard, BpmnReviewSheet } from "./review/BpmnReviewCard";

type ChatExperienceProps = {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  scope?: ChatScope;
};

const DEFAULT_SCOPE: ChatScope = { type: "consultant" };

/**
 * Thin container: wires the session / stream / review hooks to the presentational
 * `ChatShell`. All networking lives in `features/chat/api.ts`; all state lives in
 * the hooks under `features/chat/hooks/`.
 */
export const ChatExperience: React.FC<ChatExperienceProps> = ({
  chrome = "full",
  layout = "standalone",
  scope = DEFAULT_SCOPE,
}) => {
  const [selectedModel, setSelectedModel] = useState("gpt-5.6-luna");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isReviewOpen, setIsReviewOpen] = useState(false);
  const lastReviewTimestamp = useRef<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(
      () => setToastMessage(null),
      2800,
    );
  }, []);

  const sessions = useChatSessions(scope, selectedModel);
  const review = useBpmnReview(scope, showToast);

  useEffect(() => {
    if (!review.review) return;

    if (review.review.updated_at !== lastReviewTimestamp.current) {
      lastReviewTimestamp.current = review.review.updated_at;
      setIsReviewOpen(true);
    }
  }, [review.review]);
  const stream = useChatStream({
    scope,
    selectedModel,
    activeSession: sessions.activeSession,
    ensureThread: sessions.ensureThread,
    selectThread: sessions.selectThread,
    commitTranscript: sessions.commitTranscript,
    onSettled: () => void review.reload(),
  });

  const showLive =
    stream.liveThreadId != null &&
    stream.liveThreadId === sessions.currentThreadId;
  const messages = showLive
    ? stream.liveMessages ?? []
    : sessions.activeSession?.messages ?? [];
  const activeTitle = sessions.activeSession
    ? sessions.activeSession.title
    : titleForScope(scope);

  const offlineMessage = stream.streamError ?? sessions.offlineMessage;
  const isOffline = Boolean(stream.streamError) || sessions.isOffline;

  return (
    <>
      <ChatShell
        chrome={chrome}
        layout={layout}
        scope={scope}
        sessions={sessions.sessions}
        currentThreadId={sessions.currentThreadId}
        messages={messages}
        activeTitle={activeTitle}
        isBusy={stream.isBusy}
        selectedModel={selectedModel}
        onNewChat={sessions.startNewThread}
        onSelectSession={sessions.selectThread}
        onDeleteSession={async (id) => {
          await sessions.deleteSession(id);
          showToast("Conversazione eliminata.");
        }}
        onClearHistory={async () => {
          await sessions.clearHistory();
          showToast("Cronologia eliminata.");
        }}
        onSearch={() => showToast("Ricerca cronologia.")}
        onConfig={() => showToast(`API backend: ${API_BASE || "locale"}`)}
        onShare={async () => {
          const text = messages
            .map((m) => `${m.role}: ${m.content}`)
            .join("\n\n");
          await navigator.clipboard?.writeText(text);
          showToast("Conversazione copiata.");
        }}
        onSelectPrompt={stream.sendMessage}
        onSendMessage={stream.sendMessage}
        onTranscribeAudio={transcribeAudio}
        onRetry={() => {
          if (stream.lastUserPrompt) void stream.sendMessage(stream.lastUserPrompt);
        }}
        onAttach={() => showToast("Carica un file audio da trascrivere.")}
        onVoice={() => showToast("Registrazione vocale pronta.")}
        onModelChange={setSelectedModel}
        reviewSlot={
          <>
            {isOffline && offlineMessage ? (
              <section className="api-status-card" role="status">
                <strong>Backend scollegato</strong>
                <p>{offlineMessage}</p>
                <button
                  type="button"
                  onClick={() => {
                    stream.clearStreamError();
                    sessions.retrySessions();
                  }}
                >
                  Riprova ora
                </button>
              </section>
            ) : null}
            {review.review ? (
              <BpmnReviewCard
                review={review.review}
                onOpen={() => setIsReviewOpen(true)}
              />
            ) : null}
          </>
        }
      />

      {review.review ? (
        <BpmnReviewSheet
          key={review.review.updated_at}
          review={review.review}
          open={isReviewOpen}
          isApproving={review.isApproving}
          isSaving={review.isSaving}
          onOpenChange={setIsReviewOpen}
          onApprove={review.approve}
          onSave={review.save}
          onToast={showToast}
        />
      ) : null}

      {toastMessage && (
        <div className="toast show" role="status">
          {toastMessage}
        </div>
      )}
    </>
  );
};
