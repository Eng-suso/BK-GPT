import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreHorizontal, Share2, Trash2, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/ui/dialog";
import { useMediaQuery } from "@/lib/useMediaQuery";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import type { ChatAttachment, ChatMode, ReasoningEffort } from "../../contracts/chat";
import type { ChatMessage, ChatSession } from "./types";
import type { ChatScope } from "./chatScope";
import { subjectForScope } from "./chatScope";
import { Sidebar } from "./navigation/Sidebar";
import { ThreadSwitcher } from "./navigation/ThreadSwitcher";
import { ChatHeader } from "./components/ChatHeader";
import { EmptyState } from "./components/EmptyState";
import { MessageList } from "./components/MessageList";
import { ChatComposer } from "./components/ChatComposer";

interface ChatShellProps {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  scope?: ChatScope;
  sessions?: ChatSession[];
  currentThreadId?: string | null;
  messages?: ChatMessage[];
  activeTitle?: string;
  isBusy?: boolean;
  /** Messaggi scritti durante il turno e non ancora partiti. */
  queuedMessages?: { content: string }[];
  onCancelQueued?: (index: number) => void;
  onStop?: () => void;
  selectedModel?: string;
  chatMode: ChatMode;
  onChatModeChange: (mode: ChatMode) => void;
  reasoningEffort: ReasoningEffort;
  onReasoningEffortChange: (effort: ReasoningEffort) => void;
  onNewChat?: () => void;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onClearHistory?: () => void;
  onSearch?: () => void;
  onConfig?: () => void;
  onShare?: () => void;
  onSelectPrompt?: (prompt: string) => void;
  onSendMessage?: (content: string, attachments: ChatAttachment[]) => void;
  onTranscribeAudio?: (file: File) => Promise<string>;
  onRetry?: () => void;
  onAttach?: () => void;
  onVoice?: () => void;
  onModelChange?: (model: string) => void;
  /** A separate workspace control rendered outside the conversation stream. */
  workspaceSlot?: React.ReactNode;
}

/**
 * La coda del turno, a vista.
 *
 * Quello che il consulente scrive mentre l'agente lavora non sparisce e non
 * scavalca la risposta: resta qui finche' il turno non si chiude, e si puo'
 * togliere se nel frattempo non serve piu'.
 */
function QueuedMessages({
  items,
  onCancel,
}: {
  items: { content: string }[];
  onCancel?: (index: number) => void;
}): React.JSX.Element | null {
  const { t } = useTranslation("chat");
  if (items.length === 0) return null;

  return (
    <section
      className="mx-auto mt-3 flex w-full max-w-[var(--chat-measure)] flex-col gap-1.5 rounded-lg border border-dashed border-border bg-muted/40 p-3"
      aria-label={t("queue.title")}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground">
        {t("queue.title")}
      </p>
      <ul className="flex flex-col gap-1.5">
        {items.map((item, index) => (
          <li
            key={`${index}-${item.content.slice(0, 24)}`}
            className="flex items-start gap-2 text-sm text-foreground"
          >
            <span className="mt-0.5 flex-none rounded border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.04em] text-muted-foreground">
              {t("status.queuedLabel")}
            </span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">
              {item.content}
            </span>
            {onCancel ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label={t("queue.remove")}
                title={t("queue.remove")}
                onClick={() => onCancel(index)}
              >
                <X />
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{t("queue.hint")}</p>
    </section>
  );
}

export const ChatShell: React.FC<ChatShellProps> = ({
  chrome = "full",
  layout = "standalone",
  scope,
  sessions = [],
  currentThreadId = null,
  messages = [],
  activeTitle = "Chat consulente",
  isBusy = false,
  queuedMessages = [],
  onCancelQueued,
  onStop,
  selectedModel = "gpt-5.6-luna",
  chatMode,
  onChatModeChange,
  reasoningEffort,
  onReasoningEffortChange,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearHistory,
  onSearch,
  onConfig,
  onShare,
  onSelectPrompt,
  onSendMessage,
  onTranscribeAudio,
  onRetry,
  onAttach,
  onVoice,
  onModelChange,
  workspaceSlot,
}) => {
  const { t, i18n } = useTranslation("chat");
  const locale = i18n.language || "it";
  const [isDrawerOpen, setIsDrawerOpen] = useState(() => window.innerWidth >= 1440);
  const compactHistory = useMediaQuery("(max-width: 1099px)");
  const historyButtonRef = useRef<HTMLButtonElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const prevMessageCount = useRef(0);
  const isEmbedded = layout === "embedded";
  const hasConversation = messages.length > 0;
  const headerTitle = hasConversation
    ? activeTitle
    : subjectForScope(
        scope ?? { type: "consultant" },
        t("scope.consultant.title"),
      );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsDrawerOpen(false);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // Follow the conversation, but don't yank the view down mid-stream if the
  // reader has scrolled up: snap only on a new message or when already near the
  // bottom. Honours reduced-motion.
  useEffect(() => {
    const grew = messages.length > prevMessageCount.current;
    prevMessageCount.current = messages.length;

    const area = scrollAreaRef.current;
    const nearBottom = area
      ? area.scrollHeight - area.scrollTop - area.clientHeight < 120
      : true;
    if (!grew && !nearBottom) return;

    const reduce = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    area?.scrollTo({
      top: area.scrollHeight,
      behavior: reduce ? "auto" : "smooth",
    });
  }, [messages]);

  if (chrome === "panel") {
    return (
      <section className="embedded-chat-panel" aria-label="Chat contestuale">
        <header className="embedded-chat-header ui-surface-toolbar flex min-h-[var(--inspector-header-height)] items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="flex min-w-0 flex-col gap-1">
            <ThreadSwitcher
              sessions={sessions}
              currentThreadId={currentThreadId}
              activeTitle={activeTitle}
              locale={locale}
              onNewChat={onNewChat}
              onSelectSession={onSelectSession}
            />
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("actions.more")}
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onShare?.()}>
                  <Share2 />
                  {t("actions.copy")}
                </DropdownMenuItem>
                {currentThreadId && onDeleteSession && (
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => onDeleteSession(currentThreadId)}
                  >
                    <Trash2 />
                    {t("threads.deleteCurrent")}
                  </DropdownMenuItem>
                )}
                {onClearHistory && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() => onClearHistory()}
                    >
                      <Trash2 />
                      {t("actions.clearHistory")}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <div className="embedded-chat-body" ref={scrollAreaRef}>
          {messages.length === 0 ? (
            <EmptyState scope={scope} onSelectPrompt={onSelectPrompt} />
          ) : (
            <MessageList messages={messages} onRetry={onRetry} />
          )}
          <QueuedMessages items={queuedMessages} onCancel={onCancelQueued} />
          <div ref={messagesEndRef} />
        </div>

        {workspaceSlot ? (
          <div className="shrink-0 border-t border-border bg-background px-4 py-2">
            {workspaceSlot}
          </div>
        ) : null}

        <ChatComposer
          scope={scope ?? { type: "consultant" }}
          selectedModel={selectedModel}
          chatMode={chatMode}
          onChatModeChange={onChatModeChange}
          reasoningEffort={reasoningEffort}
          onReasoningEffortChange={onReasoningEffortChange}
          isBusy={isBusy}
          onStop={onStop}
          onSubmit={onSendMessage}
          onTranscribeAudio={onTranscribeAudio}
          onAttach={onAttach}
          onVoice={onVoice}
          onModelChange={onModelChange}
        />
      </section>
    );
  }

  return (
    <div className={`viewport ${isEmbedded ? "viewport-embedded" : ""}`}>
      <section className={`shell ${isEmbedded ? "chat-shell-embedded" : ""} ${isDrawerOpen && !compactHistory ? "history-open" : "history-closed"}`} aria-label="Chat consulente">
        {isDrawerOpen && !compactHistory && <Sidebar
          sessions={sessions}
          currentThreadId={currentThreadId}
          locale={locale}
          isOpen={isDrawerOpen}
          onNewChat={() => {
            onNewChat?.();
          }}
          onSelectSession={(id) => {
            onSelectSession?.(id);
          }}
          onDeleteSession={onDeleteSession}
          onClearHistory={onClearHistory}
          onSearch={onSearch}
        />}
        <Dialog open={isDrawerOpen && compactHistory} onOpenChange={setIsDrawerOpen}>
          <DialogContent aria-describedby={undefined} onCloseAutoFocus={(event) => { event.preventDefault(); historyButtonRef.current?.focus(); }} className="chat-history-dialog flex h-[85dvh] flex-col overflow-hidden border-border p-4 sm:max-w-md">
            <DialogTitle>{t("sidebar.recent")}</DialogTitle>
            <Sidebar sessions={sessions} currentThreadId={currentThreadId} locale={locale} isOpen onNewChat={() => { setIsDrawerOpen(false); onNewChat?.(); }} onSelectSession={(id) => { setIsDrawerOpen(false); onSelectSession?.(id); }} onDeleteSession={onDeleteSession} onClearHistory={onClearHistory} onSearch={onSearch} />
          </DialogContent>
        </Dialog>

        <section className="main">
          <ChatHeader
            title={headerTitle}
            isDrawerOpen={isDrawerOpen}
            onMenuToggle={() => setIsDrawerOpen((prev) => !prev)}
            historyButtonRef={historyButtonRef}
            onConfig={onConfig}
            onShare={onShare}
          />

          <div className="content">
            <div className="messages" id="messages" ref={scrollAreaRef}>
              {messages.length === 0 ? (
                <EmptyState scope={scope} onSelectPrompt={onSelectPrompt} />
              ) : (
                <MessageList messages={messages} onRetry={onRetry} />
              )}
              <QueuedMessages items={queuedMessages} onCancel={onCancelQueued} />
              <div ref={messagesEndRef} />
            </div>
          </div>

          {workspaceSlot ? (
            <div className="shrink-0 border-t border-border bg-background px-4 py-2">
              {workspaceSlot}
            </div>
          ) : null}

          <ChatComposer
            scope={scope ?? { type: "consultant" }}
            selectedModel={selectedModel}
            chatMode={chatMode}
            onChatModeChange={onChatModeChange}
            reasoningEffort={reasoningEffort}
            onReasoningEffortChange={onReasoningEffortChange}
            isBusy={isBusy}
            onStop={onStop}
            onSubmit={onSendMessage}
            onTranscribeAudio={onTranscribeAudio}
            onAttach={onAttach}
            onVoice={onVoice}
            onModelChange={onModelChange}
          />
        </section>
      </section>
    </div>
  );
};
