import React, { useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatSession } from "./types";
import type { NavigationTab } from "./navigationTypes";
import { NavigationRail } from "./navigation/NavigationRail";
import { Sidebar } from "./navigation/Sidebar";
import { ChatHeader } from "./components/ChatHeader";
import { EmptyState } from "./components/EmptyState";
import { MessageList } from "./components/MessageList";
import { ChatComposer } from "./components/ChatComposer";

interface ChatShellProps {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  activeTab?: NavigationTab;
  sessions?: ChatSession[];
  currentThreadId?: string | null;
  messages?: ChatMessage[];
  activeTitle?: string;
  isBusy?: boolean;
  selectedModel?: string;
  onTabChange?: (tab: NavigationTab) => void;
  onThemeToggle?: () => void;
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
  activeTab = "chat",
  sessions = [],
  currentThreadId = null,
  messages = [],
  activeTitle = "Chat consulente",
  isBusy = false,
  selectedModel = "gpt-5.6-luna",
  onTabChange,
  onThemeToggle,
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
        <header className="embedded-chat-header">
          <div>
            <p className="product-eyebrow">Chat</p>
            <h3>{activeTitle}</h3>
          </div>
          <div className="embedded-chat-actions">
            <button type="button" onClick={onNewChat}>
              Nuova
            </button>
            <button type="button" onClick={onShare}>
              Copia
            </button>
          </div>
        </header>

        <div className="embedded-thread-bar" aria-label="Thread della chat corrente">
          <div className="embedded-thread-label">
            <span>Thread</span>
            <strong>{sessions.length}</strong>
          </div>

          <div className="embedded-thread-list">
            {sessions.length === 0 && (
              <span className="embedded-thread-empty">Nessun thread</span>
            )}
            {sessions.map((session) => {
              const isActive = session.threadId === currentThreadId;

              return (
                <div
                  key={session.threadId}
                  className={`embedded-thread-item${isActive ? " is-active" : ""}`}
                >
                  <button
                    type="button"
                    title={session.title}
                    aria-current={isActive ? "true" : undefined}
                    onClick={() => onSelectSession?.(session.threadId)}
                  >
                    {session.title}
                  </button>
                  <button
                    type="button"
                    className="embedded-thread-delete"
                    title="Elimina thread"
                    aria-label="Elimina thread"
                    onClick={() => onDeleteSession?.(session.threadId)}
                  >
                    x
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
        {!isEmbedded && (
          <NavigationRail
            activeTab={activeTab}
            onTabChange={(tab) => {
              if (tab === "chat" && window.innerWidth < 1100) {
                setIsDrawerOpen((prev) => !prev);
              }
              onTabChange?.(tab);
            }}
            onThemeToggle={onThemeToggle}
          />
        )}

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
