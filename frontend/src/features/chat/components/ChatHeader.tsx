import React from "react";
import { useTranslation } from "react-i18next";
import { Menu, MoreHorizontal, Settings, Share2 } from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";

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
  const { t } = useTranslation("chat");

  return (
    <header className="topbar">
      <div className="topbar-left">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="menu-toggle"
          onClick={() => onMenuToggle?.()}
          title={t("actions.history")}
          aria-label={t("actions.history")}
          aria-expanded={isDrawerOpen}
        >
          <Menu />
        </Button>
        <strong className="chat-title">{title}</strong>
      </div>

      <div className="topbar-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label={t("actions.more")}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onShare?.()}>
              <Share2 />
              {t("actions.copy")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onConfig?.()}>
              <Settings />
              {t("actions.config")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
};
