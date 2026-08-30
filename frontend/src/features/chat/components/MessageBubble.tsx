import React from "react";
import { marked } from "marked";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
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
      <div className="message error-bubble w-full">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-[13px] text-destructive">
          <span className="flex items-center gap-2">
            <TriangleAlert className="size-4 flex-none" />
            Non sono riuscito a completare la richiesta. Verifica la connessione
            al backend.
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-none border-destructive/30 text-destructive hover:bg-destructive/10"
            onClick={() => onRetry?.()}
          >
            Riprova
          </Button>
        </div>
      </div>
    );
  }

  if (message.role === "assistant") {
    const htmlContent = marked.parse(message.content || "") as string;
    return (
      <div className="message assistant markdown w-full max-w-full py-1 text-[14.5px] leading-relaxed text-foreground">
        {message.activity && message.activity.length > 0 ? (
          <div
            className="mb-3 flex flex-col gap-1.5 border-l-2 border-border pl-3"
            aria-label="Attivita agente"
          >
            {message.activity.map((item) => (
              <div
                key={item.key}
                className={cn(
                  "flex items-center gap-2 text-xs",
                  item.status === "running"
                    ? "text-foreground"
                    : "text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "size-1.5 flex-none rounded-full",
                    item.status === "running"
                      ? "animate-pulse bg-primary"
                      : "bg-muted-foreground/50",
                  )}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        ) : null}
        <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
      </div>
    );
  }

  return (
    <div className="message user ml-auto w-fit max-w-[75%] whitespace-pre-wrap rounded-2xl border border-border bg-muted px-3.5 py-2 text-[14.5px] leading-relaxed text-foreground">
      {message.content}
    </div>
  );
};
