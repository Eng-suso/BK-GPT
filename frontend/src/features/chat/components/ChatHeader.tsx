import React from "react";
import { Menu, Settings, Share2 } from "lucide-react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";

interface ChatHeaderProps {
  title?: string;
  isDrawerOpen?: boolean;
  onMenuToggle?: () => void;
  onConfig?: () => void;
  onShare?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  title = "Chat consulente",
  isDrawerOpen = false,
  onMenuToggle,
  onConfig,
  onShare,
}) => {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="menu-toggle"
          onClick={() => onMenuToggle?.()}
          title="Menu conversazioni"
          aria-label="Apri conversazioni"
          aria-expanded={isDrawerOpen}
        >
          <Menu />
        </Button>
        <strong className="chat-title">{title}</strong>
        <Badge variant="outline">Locale</Badge>
      </div>

      <div className="topbar-right">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onConfig?.()}
          title="Configurazione API"
        >
          <Settings />
          <span className="hidden sm:inline">Configurazione</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onShare?.()}
          title="Condividi chat"
        >
          <Share2 />
          <span className="hidden sm:inline">Condividi</span>
        </Button>
      </div>
    </header>
  );
};
