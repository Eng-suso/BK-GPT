import React, { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog, InlineNotice } from "@/components/feedback";
import { Button } from "@/ui/button";

import { ServiceStatusDialog } from "@/features/status/ServiceStatusDialog";
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
import { HistorySearchDialog } from "./navigation/HistorySearchDialog";
import { BpmnReviewSheet } from "./review/BpmnReviewCard";
import { ModelingWorkspaceBar } from "./review/ModelingWorkspaceBar";

type ChatExperienceProps = {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  scope?: ChatScope;
};

const DEFAULT_SCOPE: ChatScope = { type: "consultant" };

/** Una cancellazione in attesa di risposta: una conversazione, o tutte. */
type PendingRemoval =
  | { kind: "session"; threadId: string }
  | { kind: "history" }
  | null;

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
  const { t, i18n } = useTranslation("chat");
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
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isStatusOpen, setIsStatusOpen] = useState(false);
  /** Cosa sta per essere cancellato, finche' non c'e' una risposta. */
  const [pendingRemoval, setPendingRemoval] = useState<PendingRemoval>(null);
  /** Quale famiglia di testi usa il dialogo: una conversazione, o tutte. */
  const removalCopy =
    pendingRemoval?.kind === "history" ? "clearHistory" : "deleteSession";
  const reviewButtonRef = useRef<HTMLButtonElement | null>(null);
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
  const canModel = scope.type === "process" || scope.type === "canvas";
  // Chiudere la superficie non cancella niente: il piano vive nel backend, e
  // riaprirla lo ritrova dov'era. Una nuova versione del piano la fa tornare,
  // perche' a quel punto c'e' qualcosa di nuovo da guardare.
  //
  // La chiusura e' legata al piano *di questo processo*, non al solo numero di
  // versione: due processi diversi possono stare entrambi alla V3, e una
  // chiusura fatta sul primo spegneva la superficie anche sul secondo - un piano
  // con decisioni da prendere che non si mostrava mai.
  // Anche il "nessun piano" e' di un processo preciso. Un literal condiviso
  // faceva sparire la barra su ogni processo senza piano appena la si chiudeva
  // su uno: la chiusura viaggiava da un cliente all'altro.
  const scopeKey =
    scope.type === "canvas"
      ? scope.bpmnModelId
      : scope.type === "process"
        ? scope.processId
        : scope.type;
  const reviewIdentity = review.review
    ? `${review.review.bpmn_model_id}@${review.review.version}`
    : `no-plan@${scopeKey}`;
  const [dismissedReview, setDismissedReview] = useState<string | null>(null);
  const setIsModelingSurfaceDismissed = (dismissed: boolean) =>
    setDismissedReview(dismissed ? reviewIdentity : null);
  const showModelingSurface =
    canModel && !turnError && !historyUnavailable && dismissedReview !== reviewIdentity;

  const startModelingReview = () => {
    setChatMode("plan");
    // Attivazione esplicita: il runtime di modellazione parte da un gesto del
    // consulente o da una richiesta scritta, mai da solo perche' il turno ha
    // toccato il processo.
    setDismissedReview(null);
    void stream.sendMessage(
      "Prepara una review BPMN per questo processo usando le evidenze disponibili. Non generare ancora il canvas.",
      [],
      "plan",
    );
  };

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
        // Cancellare non parte dal click: `RecordLifecycleDialog` chiede
        // conferma per archiviare un progetto, e qui un click portava via
        // tutte le conversazioni dello spazio di lavoro.
        onDeleteSession={(id) => setPendingRemoval({ kind: "session", threadId: id })}
        onClearHistory={() => setPendingRemoval({ kind: "history" })}
        onSearch={() => setIsSearchOpen(true)}
        onConfig={() => setIsStatusOpen(true)}
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
        workspaceSlot={turnError || historyUnavailable || showModelingSurface ? (
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
            {showModelingSurface ? (
              <ModelingWorkspaceBar
                review={review.review}
                isLoadingReview={review.isLoadingReview}
                reviewError={review.reviewError}
                canModel={canModel}
                isBusy={stream.isBusy}
                openButtonRef={reviewButtonRef}
                onOpenReview={() => setIsReviewOpen(true)}
                onStartModeling={startModelingReview}
                onDismiss={() => setIsModelingSurfaceDismissed(true)}
              />
            ) : null}
          </>
        ) : undefined}
      />

      {review.review ? (
        <BpmnReviewSheet
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
          onReturnFocus={() => reviewButtonRef.current?.focus()}
        />
      ) : null}

      <HistorySearchDialog
        open={isSearchOpen}
        onOpenChange={setIsSearchOpen}
        scopeKey={sessions.scopeKey}
        currentThreadId={sessions.currentThreadId}
        locale={i18n.language || "it"}
        onSelectSession={sessions.selectThread}
      />

      <ServiceStatusDialog
        open={isStatusOpen}
        onOpenChange={setIsStatusOpen}
        modelName={selectedModel}
      />

      <ConfirmDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRemoval(null);
        }}
        destructive
        title={t(`confirm.${removalCopy}.title`)}
        description={t(`confirm.${removalCopy}.body`)}
        confirmLabel={t(`confirm.${removalCopy}.action`)}
        onConfirm={async () => {
          if (!pendingRemoval) return;
          // Se la cancellazione fallisce l'errore sale: il dialogo resta
          // aperto e lo dice, invece di chiudersi annunciando un lavoro che
          // non e' stato fatto.
          if (pendingRemoval.kind === "history") {
            await sessions.clearHistory();
          } else {
            await sessions.deleteSession(pendingRemoval.threadId);
          }
          showToast(t(`confirm.${removalCopy}.done`));
        }}
      />

      {toastMessage && (
        <div className="toast show" role="status">
          {toastMessage}
        </div>
      )}
    </>
  );
};
