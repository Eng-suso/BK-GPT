import React, { useEffect, useRef, useState } from "react";
import { ChatMessage, ChatSession } from "../../types/chat";
import { NavigationTab } from "../../types/navigation";
import { NavigationRail } from "../navigation/NavigationRail";
import { Sidebar } from "../navigation/Sidebar";
import { ChatHeader } from "../chat/ChatHeader";
import { EmptyState } from "../chat/EmptyState";
import { MessageList } from "../chat/MessageList";
import { ChatComposer } from "../chat/ChatComposer";

interface AppShellProps {
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
}

export const AppShell: React.FC<AppShellProps> = ({
  activeTab = "chat",
  sessions = [],
  currentThreadId = null,
  messages = [],
  activeTitle = "Suso GPT",
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
}) => {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  return (
    <div className="viewport">
      <main className="shell" aria-label="Suso GPT chat">
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
