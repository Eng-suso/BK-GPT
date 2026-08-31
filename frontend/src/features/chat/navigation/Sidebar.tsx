import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, Search } from "lucide-react";

import { Button } from "@/ui/button";
import type { ChatSession } from "../types";
import { ConversationList } from "./ConversationList";

interface SidebarProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
  locale: string;
  isOpen?: boolean;
  onNewChat?: () => void;
  onSelectSession?: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onClearHistory?: () => void;
  onSearch?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentThreadId,
  locale,
  isOpen = false,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearHistory,
  onSearch,
}) => {
  const { t } = useTranslation("chat");

  return (
    <aside
      className={`sidebar ${isOpen ? "open" : ""}`}
      aria-label={t("sidebar.recent")}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          {t("sidebar.title")}
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => onSearch?.()}
          title={t("actions.search")}
          aria-label={t("actions.search")}
        >
          <Search />
        </Button>
      </div>

      <Button type="button" className="mb-4 w-full" onClick={() => onNewChat?.()}>
        <Plus />
        {t("sidebar.newChat")}
      </Button>

      <ConversationList
        sessions={sessions}
        currentThreadId={currentThreadId}
        locale={locale}
        onSelectSession={onSelectSession}
        onDeleteSession={onDeleteSession}
      />

      {sessions.length > 0 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 w-full"
          onClick={() => onClearHistory?.()}
        >
          {t("actions.clearHistory")}
        </Button>
      )}
    </aside>
  );
};
