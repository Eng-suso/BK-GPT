import React from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ChatSession } from "../types";
import { formatThreadTime, groupThreadsByRecency } from "../lib/threadGroups";

interface ConversationListProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
  locale: string;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  sessions,
  currentThreadId,
  locale,
  onSelectSession,
  onDeleteSession,
}) => {
  const { t } = useTranslation("chat");
  const groups = React.useMemo(
    () => groupThreadsByRecency(sessions),
    [sessions],
  );

  if (sessions.length === 0) {
    return (
      <p className="px-2 py-6 text-center text-[13px] text-muted-foreground">
        {t("threads.empty")}
      </p>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      {groups.map((group) => (
        <section key={group.key} aria-label={t(`threads.group.${group.key}`)}>
          <h3 className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground">
            {t(`threads.group.${group.key}`)}
          </h3>
          <ul className="flex flex-col gap-0.5" role="list">
            {group.sessions.map((session) => {
              const isActive = session.threadId === currentThreadId;
              const when = formatThreadTime(session, locale);
              return (
                <li
                  key={session.threadId}
                  className={cn(
                    "group flex items-center gap-1 rounded-md border border-transparent pr-1 transition-colors hover:bg-muted",
                    isActive && "border-border bg-accent hover:bg-accent",
                  )}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-md px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => onSelectSession?.(session.threadId)}
                  >
                    <span
                      className={cn(
                        "truncate text-[13px] leading-5",
                        isActive
                          ? "font-medium text-foreground"
                          : "text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      {session.title}
                    </span>
                    {when ? (
                      <span className="text-[11px] tabular-nums text-muted-foreground/80">
                        {when}
                      </span>
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className="grid size-7 flex-none place-items-center rounded-md text-muted-foreground opacity-0 transition hover:bg-[var(--red-50)] hover:text-[var(--red-600)] focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100"
                    aria-label={`${t("threads.delete")}: ${session.title}`}
                    title={t("threads.delete")}
                    onClick={() => onDeleteSession?.(session.threadId)}
                  >
                    <X className="size-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
};
