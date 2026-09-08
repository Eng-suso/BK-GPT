import React, { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { InlineNotice } from "@/components/feedback";
import { Button } from "@/ui/button";

import { API_BASE } from "@/lib/api";
import {
  DEFAULT_CHAT_MODE,
  DEFAULT_REASONING_EFFORT,
  type ChatMode,
  type ReasoningEffort,
} from "../../contracts/chat";
import type { ChatScope } from "./chatScope";
import { titleForScope } from "./chatScope";
import { ChatShell } from "./ChatShell";
import { transcribeAudio } from "./api";
import { useBpmnReview } from "./hooks/useBpmnReview";
import { useChatSessions } from "./hooks/useChatSessions";
import { useChatStream } from "./hooks/useChatStream";
import { BpmnReviewCard, BpmnReviewSheet } from "./review/BpmnReviewCard";
import { ReviewQuestionsCard } from "./review/ReviewQuestionsCard";

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
  const { t } = useTranslation("chat");
  const [selectedModel, setSelectedModel] = useState("gpt-5.6-luna");
  // The working mode is per-conversation, not per-thread: switching it changes what
  // the next message is allowed to do, and must not fork the session.
  const [chatMode, setChatMode] = useState<ChatMode>(DEFAULT_CHAT_MODE);
  // Stessa vita della modalita': e' una preferenza di come lavorare, non una
  // proprieta' del thread.
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>(DEFAULT_REASONING_EFFORT);
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
    chatMode,
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

  // PROCESS-V2-14: due guasti diversi finivano nello stesso avviso, e un turno
  // che non ha chiuso veniva raccontato come backend irraggiungibile. Il
  // consulente andava a cercare un server spento mentre il problema era il giro
  // di lavoro precedente ancora in corso. Sono due cose, e si dicono separate.
  const turnError = stream.streamError;
  const historyUnavailable = sessions.isOffline ? sessions.offlineMessage : null;

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
        queuedMessages={stream.queuedMessages}
        onCancelQueued={stream.cancelQueuedMessage}
        onStop={stream.stopStreaming}
        selectedModel={selectedModel}
        chatMode={chatMode}
        onChatModeChange={setChatMode}
        reasoningEffort={reasoningEffort}
        onReasoningEffortChange={setReasoningEffort}
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
          if (stream.lastUserPrompt)
            void stream.sendMessage(stream.lastUserPrompt, stream.lastUserAttachments);
        }}
        onAttach={() => showToast("Carica un file audio da trascrivere.")}
        onVoice={() => showToast("Registrazione vocale pronta.")}
        onModelChange={setSelectedModel}
        reviewSlot={
          <>
            {turnError ? (
              <InlineNotice
                className="chat-service-notice"
                tone="error"
                title={t("status.requestFailed")}
                action={
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      stream.clearStreamError();
                      if (stream.lastUserPrompt)
                        void stream.sendMessage(
                          stream.lastUserPrompt,
                          stream.lastUserAttachments,
                        );
                    }}
                  >
                    {t("actions.retry")}
                  </Button>
                }
              >
                {turnError}
              </InlineNotice>
            ) : null}
            {historyUnavailable ? (
              <InlineNotice
                className="chat-service-notice"
                tone="warning"
                title={t("status.historyUnavailable")}
                action={
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => sessions.retrySessions()}
                  >
                    {t("actions.retry")}
                  </Button>
                }
              >
                {t("status.historyUnavailableBody")}
              </InlineNotice>
            ) : null}
            {review.review ? (
              <BpmnReviewCard
                review={review.review}
                isStale={Boolean(turnError)}
                onOpen={() => setIsReviewOpen(true)}
              />
            ) : null}
            {review.review?.open_questions?.length ? (
              <ReviewQuestionsCard
                questions={review.review.open_questions}
                isAnswering={review.isAnswering}
                onAnswer={review.answerQuestion}
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
          versions={review.versions}
          isApproving={review.isApproving}
          isSaving={review.isSaving}
          isAnswering={review.isAnswering}
          onOpenChange={setIsReviewOpen}
          onApprove={review.approve}
          onSave={review.save}
          onAnswer={review.answerQuestion}
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
