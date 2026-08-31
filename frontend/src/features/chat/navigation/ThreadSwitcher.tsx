import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronsUpDown, MessagesSquare, Plus } from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import type { ChatSession } from "../types";
import { formatThreadTime, groupThreadsByRecency } from "../lib/threadGroups";

interface ThreadSwitcherProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
  /** Title of the active thread; ignored when no thread is selected. */
  activeTitle?: string;
  locale: string;
  onNewChat?: () => void;
  onSelectSession?: (threadId: string) => void;
}

const GROUP_LABEL_CLASS =
  "px-2 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground";

/**
 * Compact thread control for the embedded chat panel: one trigger that opens the
 * recency-grouped thread list plus "new thread". Replaces the horizontal chip
 * strip, which shifted layout on select and truncated to nothing in a narrow
 * panel.
 */
export const ThreadSwitcher: React.FC<ThreadSwitcherProps> = ({
  sessions,
  currentThreadId,
  activeTitle,
  locale,
  onNewChat,
  onSelectSession,
}) => {
  const { t } = useTranslation("chat");
  const groups = React.useMemo(
    () => groupThreadsByRecency(sessions),
    [sessions],
  );

  if (sessions.length === 0) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="max-w-full justify-start"
        onClick={() => onNewChat?.()}
      >
        <Plus className="size-3.5" />
        <span className="truncate">{t("threads.new")}</span>
      </Button>
    );
  }

  const triggerLabel =
    currentThreadId && activeTitle ? activeTitle : t("threads.new");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="max-w-full justify-start font-medium"
          aria-label={t("threads.switch")}
        >
          <MessagesSquare className="size-3.5 text-muted-foreground" />
          <span className="truncate">{triggerLabel}</span>
          <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="max-h-[min(60vh,var(--radix-dropdown-menu-content-available-height))] w-[280px] overflow-y-auto"
      >
        <DropdownMenuItem onSelect={() => onNewChat?.()}>
          <Plus />
          {t("threads.new")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={currentThreadId ?? ""}
          onValueChange={(value) => onSelectSession?.(value)}
        >
          {groups.map((group) => (
            <React.Fragment key={group.key}>
              <DropdownMenuLabel className={GROUP_LABEL_CLASS}>
                {t(`threads.group.${group.key}`)}
              </DropdownMenuLabel>
              {group.sessions.map((session) => {
                const when = formatThreadTime(session, locale);
                return (
                  <DropdownMenuRadioItem
                    key={session.threadId}
                    value={session.threadId}
                    textValue={session.title}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {session.title}
                    </span>
                    {when ? (
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {when}
                      </span>
                    ) : null}
                  </DropdownMenuRadioItem>
                );
              })}
            </React.Fragment>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
