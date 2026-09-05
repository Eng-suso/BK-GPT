import React from "react";
import { useTranslation } from "react-i18next";
import { Bot, PencilLine, Route } from "lucide-react";

import { cn } from "@/lib/utils";
import { CHAT_MODES, type ChatMode } from "../../../contracts/chat";

type ChatModeSelectorProps = {
  value: ChatMode;
  onChange: (mode: ChatMode) => void;
  disabled?: boolean;
};

const MODE_ICONS: Record<ChatMode, React.ReactNode> = {
  plan: <Route aria-hidden="true" />,
  edit: <PencilLine aria-hidden="true" />,
  agent: <Bot aria-hidden="true" />,
};

/**
 * How much of the workflow the user hands over for the next message.
 *
 * A radiogroup rather than a dropdown: the mode changes what the agent is allowed
 * to do, so which one is active has to be readable without opening anything.
 * Arrow keys move between modes, as a radiogroup should.
 */
export const ChatModeSelector: React.FC<ChatModeSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation("chat");

  const selectRelative = (offset: number) => {
    const current = CHAT_MODES.indexOf(value);
    const next = CHAT_MODES[(current + offset + CHAT_MODES.length) % CHAT_MODES.length];
    onChange(next);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      selectRelative(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      selectRelative(-1);
    }
  };

  return (
    <div
      className="chat-mode-selector"
      role="radiogroup"
      aria-label={t("mode.label")}
      onKeyDown={handleKeyDown}
    >
      {CHAT_MODES.map((mode) => {
        const isActive = mode === value;
        return (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={isActive}
            // Roving tabindex: the group is one tab stop, arrows move inside it.
            tabIndex={isActive ? 0 : -1}
            disabled={disabled}
            // The visible label collapses to an icon on a narrow composer. Without
            // an explicit name the accessible name falls back to `title`, so a
            // screen reader would read the whole explanatory sentence instead of
            // "Plan" - the tooltip is the hint, not the name.
            aria-label={t(`mode.${mode}.label`)}
            title={t(`mode.${mode}.hint`)}
            className={cn("chat-mode-option", isActive && "is-active")}
            onClick={() => onChange(mode)}
          >
            {MODE_ICONS[mode]}
            <span>{t(`mode.${mode}.label`)}</span>
          </button>
        );
      })}
    </div>
  );
};
