import React from "react";
import { marked } from "marked";
import type { ChatMessage } from "../types";

interface MessageBubbleProps {
  message: ChatMessage;
  onRetry?: () => void;
}

marked.setOptions({
  gfm: true,
  breaks: true,
});

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, onRetry }) => {
  if (message.role === "error") {
    return (
      <div className="message error-bubble">
        <div className="error-bubble-inner">
          <span>⚠️ Non sono riuscito a completare la richiesta. Verifica la connessione al backend.</span>
          <button className="retry-btn" type="button" onClick={() => onRetry?.()}>
            Riprova
          </button>
        </div>
      </div>
    );
  }

  if (message.role === "assistant") {
    const htmlContent = marked.parse(message.content || "") as string;
    return (
      <div className="message assistant markdown">
        {message.activity && message.activity.length > 0 ? (
          <div className="agent-activity" aria-label="Attivita agente">
            {message.activity.map((item) => (
              <div
                key={item.key}
                className={`agent-activity-item agent-activity-item-${item.status}`}
              >
                <span className="agent-activity-dot" aria-hidden="true" />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        ) : null}
        <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
      </div>
    );
  }

  return <div className="message user">{message.content}</div>;
};
