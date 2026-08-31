import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreHorizontal, Plus, Share2, Trash2, X } from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatSession } from "./types";
import type { ChatScope } from "./chatScope";
import { subjectForScope } from "./chatScope";
import { Sidebar } from "./navigation/Sidebar";
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
  selectedModel?: string;
  onNewChat?: () => void;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onClearHistory?: () => void;
  onSearch?: () => void;
  onConfig?: () => void;
  onShare?: () => void;
  onSelectPrompt?: (prompt: string) => void;
  onSendMessage?: (content: string) => void;
  onTranscribeAudio?: (file: File) => Promise<string>;
  onRetry?: () => void;
  onAttach?: () => void;
  onVoice?: () => void;
  onModelChange?: (model: string) => void;
  reviewSlot?: React.ReactNode;
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
  selectedModel = "gpt-5.6-luna",
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
  reviewSlot,
}) => {
  const { t } = useTranslation("chat");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
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

    const handleResize = () => {
      if (window.innerWidth >= 1100) {
        setIsDrawerOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (chrome === "panel") {
    return (
      <section className="embedded-chat-panel" aria-label="Chat contestuale">
        <header className="embedded-chat-header flex min-h-[var(--inspector-header-height)] items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <p className="eyebrow">{t("header.eyebrow")}</p>
            <h3 className="mt-0.5 truncate text-sm font-semibold text-foreground">
              {headerTitle}
            </h3>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button type="button" variant="outline" size="sm" onClick={onNewChat}>
              <Plus className="size-3.5" />
              {t("actions.new")}
            </Button>
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
                {onClearHistory && (
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => onClearHistory()}
                  >
                    <Trash2 />
                    {t("actions.clearHistory")}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {sessions.length > 0 && (
          <div
            className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-1.5"
            aria-label={t("threads.label")}
          >
            <span className="eyebrow shrink-0">{t("threads.label")}</span>
            <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
              {sessions.map((session) => {
                const isActive = session.threadId === currentThreadId;
                return (
                  <span
                    key={session.threadId}
                    className={cn(
                      "inline-flex flex-none items-center rounded-md border",
                      isActive
                        ? "border-border bg-card"
                        : "border-transparent",
                    )}
                  >
                    <button
                      type="button"
                      title={session.title}
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => onSelectSession?.(session.threadId)}
                      className={cn(
                        "max-w-[160px] truncate rounded-md px-2 py-1 text-xs leading-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isActive
                          ? "font-medium text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {session.title}
                    </button>
                    {isActive && (
                      <button
                        type="button"
                        aria-label={t("threads.delete")}
                        onClick={() => onDeleteSession?.(session.threadId)}
                        className="mr-0.5 grid size-5 flex-none place-items-center rounded text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <X className="size-3" />
                      </button>
                    )}
                  </span>
                );
              })}
              <button
                type="button"
                onClick={() => onNewChat?.()}
                className="inline-flex flex-none items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Plus className="size-3" />
                {t("threads.new")}
              </button>
            </div>
          </div>
        )}

        <div className="embedded-chat-body">
          {messages.length === 0 ? (
            <EmptyState scope={scope} onSelectPrompt={onSelectPrompt} />
          ) : (
            <MessageList messages={messages} onRetry={onRetry} />
          )}
          {reviewSlot}
          <div ref={messagesEndRef} />
        </div>

        <ChatComposer
          selectedModel={selectedModel}
          isBusy={isBusy}
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
      <main className={`shell ${isEmbedded ? "chat-shell-embedded" : ""}`} aria-label="Chat consulente">
        <Sidebar
          sessions={sessions}
          currentThreadId={currentThreadId}
          isOpen={isDrawerOpen}
          onNewChat={() => {
            setIsDrawerOpen(false);
            onNewChat?.();
          }}
          onSelectSession={(id) => {
            setIsDrawerOpen(false);
            onSelectSession?.(id);
          }}
          onDeleteSession={onDeleteSession}
          onClearHistory={onClearHistory}
          onSearch={onSearch}
        />

        <div
          className={`sidebar-backdrop ${isDrawerOpen ? "open" : ""}`}
          onClick={() => setIsDrawerOpen(false)}
        />

        <section className="main">
          <ChatHeader
            title={headerTitle}
            isDrawerOpen={isDrawerOpen}
            onMenuToggle={() => setIsDrawerOpen((prev) => !prev)}
            onConfig={onConfig}
            onShare={onShare}
          />

          <div className="content">
            <div className="messages" id="messages">
              {messages.length === 0 ? (
                <EmptyState scope={scope} onSelectPrompt={onSelectPrompt} />
              ) : (
                <MessageList messages={messages} onRetry={onRetry} />
              )}
              {reviewSlot}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <ChatComposer
            selectedModel={selectedModel}
            isBusy={isBusy}
            onSubmit={onSendMessage}
            onTranscribeAudio={onTranscribeAudio}
            onAttach={onAttach}
            onVoice={onVoice}
            onModelChange={onModelChange}
          />
        </section>
      </main>
    </div>
  );
};
