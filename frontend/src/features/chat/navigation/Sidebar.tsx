import React from "react";
import type { ChatSession } from "../types";
import { ConversationList } from "./ConversationList";

interface SidebarProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
  isOpen?: boolean;
  onNewChat?: () => void;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onClearHistory?: () => void;
  onSearch?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentThreadId,
  isOpen = false,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearHistory,
  onSearch,
}) => {
  return (
    <aside className={`sidebar ${isOpen ? "open" : ""}`} aria-label="Conversazioni recenti">
      <div className="sidebar-header">
        <h2 className="sidebar-title">Chat</h2>
        <button
          type="button"
          className="icon-btn"
          onClick={() => onSearch?.()}
          title="Cerca conversazione"
          aria-label="Cerca conversazione"
        >
          <svg viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </button>
      </div>

      <button type="button" className="btn-new-chat" onClick={() => onNewChat?.()}>
        <span>+</span>
        <span>Nuova chat</span>
      </button>

      <div className="section-label">
        <span>Recenti</span>
        <span>{sessions.length}</span>
      </div>

      <ConversationList
        sessions={sessions}
        currentThreadId={currentThreadId}
        onSelectSession={onSelectSession}
        onDeleteSession={onDeleteSession}
      />

      <button type="button" className="btn-clear-history" onClick={() => onClearHistory?.()}>
        Pulisci cronologia
      </button>
    </aside>
  );
};
