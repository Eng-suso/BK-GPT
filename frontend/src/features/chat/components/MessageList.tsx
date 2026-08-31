import React from "react";
import type { ChatMessage } from "../types";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
  onRetry?: () => void;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, onRetry }) => {
  return (
    <div className="message-list" id="messageList">
      {messages.map((message, index) => (
        <MessageBubble
          key={message.id || index}
          message={message}
          isLast={index === messages.length - 1}
          onRetry={onRetry}
        />
      ))}
    </div>
  );
};
