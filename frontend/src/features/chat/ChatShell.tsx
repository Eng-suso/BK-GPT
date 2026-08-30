import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatSession } from "./types";
import { Sidebar } from "./navigation/Sidebar";
import { ChatHeader } from "./components/ChatHeader";
import { EmptyState } from "./components/EmptyState";
import { MessageList } from "./components/MessageList";
import { ChatComposer } from "./components/ChatComposer";

interface ChatShellProps {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
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
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isEmbedded = layout === "embedded";

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
        <header className="embedded-chat-header flex min-h-14 items-center justify-between gap-3 border-b border-border px-3.5 py-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Chat
            </p>
            <h3 className="mt-0.5 text-sm font-semibold leading-tight text-foreground">
              {activeTitle}
            </h3>
          </div>
          <div className="flex items-center gap-1.5">
            <Button type="button" variant="outline" size="sm" onClick={onNewChat}>
              Nuova
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onShare}>
              Copia
            </Button>
          </div>
        </header>

        <div
          className="flex items-start gap-2.5 border-b border-border bg-muted/40 px-3.5 py-2.5"
          aria-label="Thread della chat corrente"
        >
          <div className="flex flex-col gap-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Thread</span>
            <strong className="text-[13px] text-foreground">
              {sessions.length}
            </strong>
          </div>

          <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5">
            {sessions.length === 0 && (
              <span className="inline-flex min-h-7 items-center text-xs text-muted-foreground">
                Nessun thread
              </span>
            )}
            {sessions.map((session) => {
              const isActive = session.threadId === currentThreadId;

              return (
                <div
                  key={session.threadId}
                  className={cn(
                    "flex max-w-[210px] flex-none items-center overflow-hidden rounded-full border border-border bg-card",
                    isActive && "border-primary bg-accent",
                  )}
                >
                  <button
                    type="button"
                    title={session.title}
                    aria-current={isActive ? "true" : undefined}
                    onClick={() => onSelectSession?.(session.threadId)}
                    className={cn(
                      "min-w-0 max-w-[170px] truncate py-0 pr-2 pl-2.5 text-xs font-semibold leading-7",
                      isActive ? "text-primary" : "text-foreground",
                    )}
                  >
                    {session.title}
                  </button>
                  <button
                    type="button"
                    title="Elimina thread"
                    aria-label="Elimina thread"
                    onClick={() => onDeleteSession?.(session.threadId)}
                    className="mr-0.5 grid size-6 flex-none place-items-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div className="embedded-chat-body">
          {messages.length === 0 ? (
            <EmptyState onSelectPrompt={onSelectPrompt} />
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
            title={activeTitle}
            isDrawerOpen={isDrawerOpen}
            onMenuToggle={() => setIsDrawerOpen((prev) => !prev)}
            onConfig={onConfig}
            onShare={onShare}
          />

          <div className="content">
            <div className="messages" id="messages">
              {messages.length === 0 ? (
                <EmptyState onSelectPrompt={onSelectPrompt} />
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
