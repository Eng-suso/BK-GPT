import React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
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
    <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto" role="list">
      {sessions.map((session) => {
        const isActive = session.threadId === currentThreadId;
        const initial = session.title
          ? session.title.charAt(0).toUpperCase()
          : "C";

        return (
          <li
            key={session.threadId}
            className={cn(
              "group flex h-9 w-full items-center gap-2 rounded-md border border-transparent px-2.5 transition-colors hover:bg-muted",
              isActive && "bg-accent",
            )}
          >
            <button
              type="button"
              className={cn(
                "flex h-full min-w-0 flex-1 items-center gap-2 text-left text-[13px] text-muted-foreground",
                isActive
                  ? "font-medium text-primary"
                  : "group-hover:text-foreground",
              )}
              aria-label={session.title}
              aria-current={isActive ? "page" : undefined}
              onClick={() => onSelectSession?.(session.threadId)}
            >
              <span
                className="grid size-[22px] flex-none place-items-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground"
                aria-hidden="true"
              >
                {initial}
              </span>
              <span className="flex-1 truncate">{session.title}</span>
            </button>
            <button
              type="button"
              className="grid size-[22px] flex-none place-items-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-[var(--red-50)] hover:text-[var(--red-600)] group-hover:opacity-100 focus-visible:opacity-100"
              aria-label="Elimina conversazione"
              title="Elimina conversazione"
              onClick={() => onDeleteSession?.(session.threadId)}
            >
              <X className="size-4" />
            </button>
          </li>
        );
      })}
    </ul>
  );
};
