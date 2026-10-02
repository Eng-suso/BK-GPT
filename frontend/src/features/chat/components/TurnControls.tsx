import React from "react";
import { useTranslation } from "react-i18next";
import { Brain, ChevronDown, Compass, ShieldCheck } from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import {
  CHAT_AUTONOMIES,
  CHAT_POSTURES_BY_SCOPE,
  REASONING_EFFORTS,
  type ChatAutonomy,
  type ChatPosture,
  type ChatScopeType,
  type ReasoningEffort,
} from "../../../contracts/chat";

type Option<T extends string> = { value: T; label: string; hint: string };

/**
 * Un selettore della barra del composer: un pulsante che dice la scelta fatta,
 * un menu con le alternative e cosa cambiano.
 */
function ChoiceMenu<T extends string>({
  icon,
  menuLabel,
  triggerLabel,
  value,
  options,
  onChange,
  disabled,
}: {
  icon: React.ReactNode;
  menuLabel: string;
  triggerLabel: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
}): React.JSX.Element {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          className="chat-mode-trigger"
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          // Il nome accessibile porta lo stato: chi ascolta lo schermo sente la
          // scelta attiva senza aprire il menu.
          aria-label={`${menuLabel}: ${triggerLabel}`}
        >
          {icon}
          <span className="chat-mode-trigger-label">{triggerLabel}</span>
          <ChevronDown className="chat-mode-trigger-caret" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="chat-mode-menu">
        <DropdownMenuLabel>{menuLabel}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => onChange(next as T)}>
          {options.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value} className="chat-mode-item">
              <span className="chat-mode-item-text">
                <span className="chat-mode-item-title">{option.label}</span>
                <span className="chat-mode-item-hint">{option.hint}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * La postura del turno: che lavoro sta facendo il consulente.
 *
 * In "auto" il pulsante mostra la postura che DeliR ha usato davvero per
 * l'ultima risposta ("Discover · auto"), cosi' il consulente vede come e' stata
 * letta la richiesta senza doverla scegliere.
 */
export function PostureSelector({
  scopeType,
  value,
  detected,
  onChange,
  disabled,
}: {
  scopeType: ChatScopeType;
  value: ChatPosture;
  detected: ChatPosture | null;
  onChange: (posture: ChatPosture) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const { t } = useTranslation("chat");
  const postures: ChatPosture[] = ["auto", ...CHAT_POSTURES_BY_SCOPE[scopeType]];
  const triggerLabel =
    value !== "auto"
      ? t(`posture.${value}.label`)
      : detected && detected !== "auto"
        ? `${t(`posture.${detected}.label`)} · ${t("posture.autoTag")}`
        : t("posture.auto.label");
  return (
    <ChoiceMenu
      icon={<Compass aria-hidden="true" />}
      menuLabel={t("posture.label")}
      triggerLabel={triggerLabel}
      value={value}
      options={postures.map((posture) => ({
        value: posture,
        label: t(`posture.${posture}.label`),
        hint: t(`posture.${posture}.hint`),
      }))}
      onChange={onChange}
      disabled={disabled}
    />
  );
}

/** Quanto ragiona il modello: un controllo a parte, sempre visibile. */
export function ReasoningSelector({
  value,
  onChange,
  disabled,
}: {
  value: ReasoningEffort;
  onChange: (effort: ReasoningEffort) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const { t } = useTranslation("chat");
  return (
    <ChoiceMenu
      icon={<Brain aria-hidden="true" />}
      menuLabel={t("effort.label")}
      triggerLabel={`${t("effort.label")}: ${t(`effort.${value}.label`)}`}
      value={value}
      options={REASONING_EFFORTS.map((level) => ({
        value: level,
        label: t(`effort.${level}.label`),
        hint: t(`effort.${level}.hint`),
      }))}
      onChange={onChange}
      disabled={disabled}
    />
  );
}

/** Quanto DeliR puo' fare da solo: decide se una scrittura parte, aspetta o no. */
export function AutonomySelector({
  value,
  onChange,
  disabled,
}: {
  value: ChatAutonomy;
  onChange: (autonomy: ChatAutonomy) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const { t } = useTranslation("chat");
  return (
    <ChoiceMenu
      icon={<ShieldCheck aria-hidden="true" />}
      menuLabel={t("autonomy.label")}
      triggerLabel={t(`autonomy.${value}.label`)}
      value={value}
      options={CHAT_AUTONOMIES.map((level) => ({
        value: level,
        label: t(`autonomy.${level}.label`),
        hint: t(`autonomy.${level}.hint`),
      }))}
      onChange={onChange}
      disabled={disabled}
    />
  );
}
