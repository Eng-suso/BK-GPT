import React from "react";
import {
  BrainCircuit,
  Check,
  CheckCircle2,
  CircleHelp,
  Copy,
  DraftingCompass,
  FileText,
  FolderOpen,
  GitCompare,
  Hammer,
  History,
  Map,
  PenLine,
  PencilRuler,
  RefreshCw,
  Route,
  Search,
  SearchCheck,
  Sparkles,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { AgentActivity, ChatMessage } from "../types";
import { activityDurationMs, formatElapsed } from "../lib/agentActivity";
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

function ActivityIcon({ icon, running }: { icon?: string; running: boolean }) {
  const className = cn("size-3.5 flex-none", running ? "text-primary" : "text-muted-foreground");
  switch (icon) {
    case "layout":
      return <Map className={className} aria-hidden="true" />;
    case "route":
      return <Route className={className} aria-hidden="true" />;
    case "edit":
      return <Wrench className={className} aria-hidden="true" />;
    case "build":
      return <Hammer className={className} aria-hidden="true" />;
    case "compass":
      return <DraftingCompass className={className} aria-hidden="true" />;
    case "draw":
      return <PencilRuler className={className} aria-hidden="true" />;
    case "check":
      return <SearchCheck className={className} aria-hidden="true" />;
    case "help":
      return <CircleHelp className={className} aria-hidden="true" />;
    case "recall":
      return <History className={className} aria-hidden="true" />;
    case "folder":
      return <FolderOpen className={className} aria-hidden="true" />;
    case "document":
      return <FileText className={className} aria-hidden="true" />;
    case "search":
      return <Search className={className} aria-hidden="true" />;
    case "extract":
      return <Sparkles className={className} aria-hidden="true" />;
    case "compare":
      return <GitCompare className={className} aria-hidden="true" />;
    case "pen":
      return <PenLine className={className} aria-hidden="true" />;
    default:
      return <BrainCircuit className={className} aria-hidden="true" />;
  }
}

/**
 * La traccia di lavoro che il consulente puo' leggere.
 *
 * Una riga per fase, con quanto e' durata. Il passo in corso ha un cronometro
 * che scorre: e' l'informazione che mancava quando l'agente restava zitto per
 * venti secondi dentro una ricerca in memoria.
 */
function ActivityTimeline({
  activity,
  label,
}: {
  activity: AgentActivity[];
  label: string;
}): React.JSX.Element {
  const hasRunning = activity.some((item) => item.status === "running");
  const [now, setNow] = React.useState(() => Date.now());

  React.useEffect(() => {
    if (!hasRunning) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasRunning]);

  return (
    <div
      className="mb-3 flex flex-col gap-1.5 border-l-2 border-border pl-3"
      aria-label={label}
    >
      {activity.map((item) => {
        const running = item.status === "running";
        const elapsed = formatElapsed(activityDurationMs(item, now));
        return (
          <div
            key={item.key}
            className={cn(
              "flex items-center gap-2 text-xs",
              running ? "text-foreground" : "text-muted-foreground",
            )}
          >
            {running ? (
              <span className="flex size-4 flex-none items-center justify-center rounded-full bg-primary/10">
                <ActivityIcon icon={item.icon} running />
              </span>
            ) : (
              <CheckCircle2
                className="size-3.5 flex-none text-muted-foreground"
                aria-hidden="true"
              />
            )}
            <span className="min-w-0 truncate">
              {item.label}
              {item.detail ? (
                <span className="text-muted-foreground"> · {item.detail}</span>
              ) : null}
            </span>
            <span className="ml-auto flex-none tabular-nums text-[11px] text-muted-foreground">
              {elapsed}
            </span>
          </div>
        );
      })}
    </div>
  );
}

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
          <ActivityTimeline
            activity={message.activity}
            label={t("status.progressLabel")}
          />
        ) : null}

        <div dangerouslySetInnerHTML={{ __html: htmlContent }} />

        {message.stoppedByUser ? (
          <p className="mt-2 text-xs text-muted-foreground">
            {t("status.stoppedByUser")}
          </p>
        ) : null}
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
