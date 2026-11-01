import React from "react";
import { useTranslation } from "react-i18next";
import { PanelLeft, MoreHorizontal, Settings, Share2 } from "lucide-react";

import { Button } from "@/ui/button";
import { WorkspaceContextBar } from "@/components/layout/CanvasWorkspace";
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
  historyButtonRef?: React.Ref<HTMLButtonElement>;
  onConfig?: () => void;
  onShare?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  title,
  isDrawerOpen = false,
  onMenuToggle,
  historyButtonRef,
  onConfig,
  onShare,
}) => {
  const { t } = useTranslation("chat");

  return (
    <WorkspaceContextBar
      title={title ?? t("scope.consultant.title")}
      navigation={<Button type="button" variant="ghost" size="icon" className="menu-toggle" ref={historyButtonRef} onClick={() => onMenuToggle?.()} title={t("actions.history")} aria-label={t("actions.history")} aria-expanded={isDrawerOpen}><PanelLeft aria-hidden="true" /></Button>}
      actions={
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
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
      }
    />
  );
};
