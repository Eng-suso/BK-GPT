import React from "react";
import { useTranslation } from "react-i18next";
import { Gauge, SlidersHorizontal } from "lucide-react";

import { Button } from "@/ui/button";

import type { Perspective } from "./perspective";

const OPTIONS = [["consultant", SlidersHorizontal], ["operations", Gauge]] as const;

/**
 * SIM-21: sceglie la prospettiva sullo stesso stato. Non modifica lo scenario
 * e non avvia un run; lo dice la descrizione collegata al gruppo.
 */
export function PerspectiveSwitch({ value, onChange }: { value: Perspective; onChange: (next: Perspective) => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  const hintId = React.useId();
  return (
    <div role="group" aria-label={t("simulation.perspective.label")} aria-describedby={hintId} className="sim-perspective-switch" data-sim-perspective={value}>
      <span id={hintId} className="sr-only">{t("simulation.perspective.hint")}</span>
      {OPTIONS.map(([option, Icon]) => (
        <Button
          key={option}
          type="button"
          size="sm"
          variant={value === option ? "secondary" : "ghost"}
          aria-pressed={value === option}
          aria-label={t(`simulation.perspective.${option}`)}
          title={t(`simulation.perspective.${option}Hint`)}
          onClick={() => { if (value !== option) onChange(option); }}
        >
          <Icon aria-hidden className="size-4" />
          <span>{t(`simulation.perspective.${option}`)}</span>
        </Button>
      ))}
    </div>
  );
}
