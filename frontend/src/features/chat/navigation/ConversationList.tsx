import React from "react";
import type { ChatSession } from "../types";

interface ConversationListProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  sessions,
  currentThreadId,
  onSelectSession,
  onDeleteSession,
}) => {
  return (
    <ul className="history-list" role="list">
      {sessions.map((session) => {
        const isActive = session.threadId === currentThreadId;
        const initial = session.title ? session.title.charAt(0).toUpperCase() : "C";

        return (
          <li
            key={session.threadId}
            className={`history-item ${isActive ? "active" : ""}`}
          >
            <button
              type="button"
              className="history-select-btn"
              aria-label={session.title}
              aria-current={isActive ? "page" : undefined}
              onClick={() => onSelectSession?.(session.threadId)}
            >
              <span className="history-avatar" aria-hidden="true">{initial}</span>
              <span className="history-text">{session.title}</span>
            </button>
            <button
              type="button"
              className="delete-btn"
              aria-label="Elimina conversazione"
              title="Elimina conversazione"
              onClick={() => onDeleteSession?.(session.threadId)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </li>
        );
      })}
    </ul>
  );
};
