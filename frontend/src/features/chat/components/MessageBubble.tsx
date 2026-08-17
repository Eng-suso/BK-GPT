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
      <div
        className="message assistant markdown"
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    );
  }

  return <div className="message user">{message.content}</div>;
};
