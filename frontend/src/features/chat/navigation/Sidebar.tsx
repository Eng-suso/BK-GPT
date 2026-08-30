import React from "react";
import { Plus, Search } from "lucide-react";

import { Button } from "@/ui/button";
import type { ChatSession } from "../types";
import { ConversationList } from "./ConversationList";

interface SidebarProps {
  sessions: ChatSession[];
  currentThreadId: string | null;
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
  isOpen = false,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearHistory,
  onSearch,
}) => {
  return (
    <aside
      className={`sidebar ${isOpen ? "open" : ""}`}
      aria-label="Conversazioni recenti"
    >
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Chat</h2>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => onSearch?.()}
          title="Cerca conversazione"
          aria-label="Cerca conversazione"
        >
          <Search />
        </Button>
      </div>

      <Button
        type="button"
        className="mb-3.5 w-full"
        onClick={() => onNewChat?.()}
      >
        <Plus />
        Nuova chat
      </Button>

      <div className="mx-1 mt-3 mb-2 flex items-center justify-between text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground">
        <span>Recenti</span>
        <span>{sessions.length}</span>
      </div>

      <ConversationList
        sessions={sessions}
        currentThreadId={currentThreadId}
        onSelectSession={onSelectSession}
        onDeleteSession={onDeleteSession}
      />

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-auto w-full"
        onClick={() => onClearHistory?.()}
      >
        Pulisci cronologia
      </Button>
    </aside>
  );
};
