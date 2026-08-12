import React from "react";
import { ChatSession } from "../../types/chat";

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
    <div className="history-list">
      {sessions.map((session) => {
        const isActive = session.threadId === currentThreadId;
        const initial = session.title ? session.title.charAt(0).toUpperCase() : "C";

        return (
          <button
            key={session.threadId}
            type="button"
            className={`history-item ${isActive ? "active" : ""}`}
            title={session.title}
            onClick={() => onSelectSession?.(session.threadId)}
          >
            <span className="history-avatar">{initial}</span>
            <span className="history-text">{session.title}</span>
            <button
              type="button"
              className="delete-btn"
              title="Elimina conversazione"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteSession?.(session.threadId);
              }}
            >
              <svg viewBox="0 0 24 24">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </button>
        );
      })}
    </div>
  );
};
