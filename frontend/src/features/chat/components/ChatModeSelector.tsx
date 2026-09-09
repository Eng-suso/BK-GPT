import React from "react";
import { useTranslation } from "react-i18next";
import { Bot, ChevronDown, MessageCircle, PencilLine, Route } from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import {
  CHAT_MODES,
  REASONING_EFFORTS,
  type ChatMode,
  type ReasoningEffort,
} from "../../../contracts/chat";

type ChatModeSelectorProps = {
  value: ChatMode;
  onChange: (mode: ChatMode) => void;
  effort: ReasoningEffort;
  onEffortChange: (effort: ReasoningEffort) => void;
  disabled?: boolean;
};

const MODE_ICONS: Record<ChatMode, React.ReactNode> = {
  conversation: <MessageCircle aria-hidden="true" />,
  plan: <Route aria-hidden="true" />,
  edit: <PencilLine aria-hidden="true" />,
  agent: <Bot aria-hidden="true" />,
};

/**
 * Modalita' di lavoro ed effort di ragionamento, in un menu solo.
 *
 * Tre pulsanti sempre a vista dicevano al consulente cosa *potrebbe* scegliere;
 * qui la barra dice cosa ha scelto, e le alternative — con la spiegazione di
 * cosa cambia — stanno a un click. L'effort vive nello stesso menu perche' e'
 * la seconda meta' della stessa decisione: quanto lo lascio lavorare.
 */
export const ChatModeSelector: React.FC<ChatModeSelectorProps> = ({
  value,
  onChange,
  effort,
  onEffortChange,
  disabled = false,
}) => {
  const { t } = useTranslation("chat");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          className="chat-mode-trigger"
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          // Il nome accessibile porta con se' lo stato: chi ascolta lo schermo
          // sente quale modalita' e' attiva senza aprire il menu.
          aria-label={`${t("mode.label")}: ${t(`mode.${value}.label`)}`}
        >
          {MODE_ICONS[value]}
          <span className="chat-mode-trigger-label">{t(`mode.${value}.label`)}</span>
          <ChevronDown className="chat-mode-trigger-caret" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" side="top" className="chat-mode-menu">
        <DropdownMenuLabel>{t("mode.label")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(next as ChatMode)}
        >
          {CHAT_MODES.map((mode) => (
            <DropdownMenuRadioItem key={mode} value={mode} className="chat-mode-item">
              <span className="chat-mode-item-icon">{MODE_ICONS[mode]}</span>
              <span className="chat-mode-item-text">
                <span className="chat-mode-item-title">{t(`mode.${mode}.label`)}</span>
                <span className="chat-mode-item-hint">{t(`mode.${mode}.hint`)}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />

        {/* Non e' una voce del menu: sceglierlo non deve chiudere il menu, cosi'
            si puo' regolare effort e modalita' nello stesso passaggio. */}
        <div className="chat-effort">
          <span className="chat-effort-label" id="chat-effort-label">
            {t("effort.label")}
          </span>
          <div
            className="chat-effort-levels"
            role="radiogroup"
            aria-labelledby="chat-effort-label"
          >
            {REASONING_EFFORTS.map((level) => (
              <button
                key={level}
                type="button"
                role="radio"
                aria-checked={level === effort}
                className={`chat-effort-level${level === effort ? " is-active" : ""}`}
                title={t(`effort.${level}.hint`)}
                onClick={() => onEffortChange(level)}
              >
                {t(`effort.${level}.label`)}
              </button>
            ))}
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
