import React from "react";
import { Check, Copy, RefreshCw, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "../types";
import { renderMarkdown } from "../lib/markdown";

interface MessageBubbleProps {
  message: ChatMessage;
  /** True for the last message in the list — gates the retry action. */
  isLast?: boolean;
  onRetry?: () => void;
}

function formatClock(iso: string | undefined, locale: string): string {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(ms);
}

const META_LABEL_CLASS =
  "text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground";

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  isLast,
  onRetry,
}) => {
  const { t, i18n } = useTranslation("chat");
  const locale = i18n.language || "it";
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(message.content || "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  };

  if (message.role === "error") {
    return (
      <div className="message error-bubble w-full">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-[13px] text-destructive">
          <span className="flex items-center gap-2">
            <TriangleAlert className="size-4 flex-none" />
            {message.content ||
              "Non sono riuscito a completare la richiesta. Verifica la connessione al backend."}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-none border-destructive/30 text-destructive hover:bg-destructive/10"
            onClick={() => onRetry?.()}
          >
            {t("actions.retry")}
          </Button>
        </div>
      </div>
    );
  }

  const time = formatClock(message.createdAt, locale);

  if (message.role === "assistant") {
    const htmlContent = renderMarkdown(message.content);
    const hasBody = Boolean(message.content?.trim());
    return (
      <div className="message assistant markdown group/msg w-full max-w-full text-sm leading-relaxed text-foreground">
        <div className="mb-1.5 flex items-center gap-2 leading-none">
          <span className={META_LABEL_CLASS}>{t("message.assistant")}</span>
          {time ? (
            <span className="text-[11px] tabular-nums text-muted-foreground">
              {time}
            </span>
          ) : null}
          {hasBody ? (
            <div className="ml-auto flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/msg:opacity-100">
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={copy}
                aria-label={t("actions.copyMessage")}
                title={t("actions.copyMessage")}
              >
                {copied ? <Check /> : <Copy />}
              </Button>
              {isLast && onRetry ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => onRetry()}
                  aria-label={t("actions.retry")}
                  title={t("actions.retry")}
                >
                  <RefreshCw />
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>

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
    <div className="message user ml-auto flex w-fit flex-col items-end">
      <div className="mb-1 flex items-center gap-2 pr-0.5 leading-none">
        <span className={META_LABEL_CLASS}>{t("message.you")}</span>
        {time ? (
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {time}
          </span>
        ) : null}
      </div>
      <div className="whitespace-pre-wrap rounded-lg border border-border bg-muted px-3 py-2 text-sm leading-relaxed text-foreground">
        {message.content}
      </div>
    </div>
  );
};
