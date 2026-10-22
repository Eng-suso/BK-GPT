import React from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";

import { TaskDurationFields } from "./TaskDurationFields";
import { formatParameterDuration } from "./studio/activityParameters";
import type { DurationDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

type TemplateWait = NonNullable<ScenarioTemplate["waits"]>[number];

/** Un'attesa nuova parte da un giorno, esponenziale: le risposte arrivano a qualsiasi distanza. */
const NEW_WAIT: DurationDraft = { meanMinutes: 1440, distribution: "expon" };

/**
 * SIM-11c/d: gli eventi intermedi che il caso aspetta. Un timer ha la durata
 * scritta nel BPMN; per un messaggio o un segnale la imposta il consulente, e
 * finché non la imposta il caso prosegue subito.
 */
export function WaitsSection({ waits, values, onChange }: {
  waits: TemplateWait[];
  values: Record<string, DurationDraft>;
  onChange: (next: Record<string, DurationDraft>) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("en") ? "en" : "it";
  const set = (id: string, value: DurationDraft | undefined) => {
    const others = Object.fromEntries(Object.entries(values).filter(([key]) => key !== id));
    onChange(value ? { ...others, [id]: value } : others);
  };

  return (
    <div className="grid gap-2" data-sim-waits>
      <p className="text-xs text-muted-foreground">{t("simulation.config.waits.hint")}</p>
      <ul className="grid gap-2">
        {waits.map((wait) => {
          const value = values[wait.element_id];
          return (
            <li key={wait.element_id} className="grid gap-2 rounded-md border border-border bg-card p-2.5" data-sim-wait={wait.element_id}>
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-foreground">{wait.name}</p>
                <span className="text-xs text-muted-foreground">{t(`simulation.config.waits.kind.${wait.kind}`)}</span>
              </div>
              {wait.kind === "timer" ? (
                <p className="text-xs text-muted-foreground">
                  {t("simulation.config.waits.timer", { duration: formatParameterDuration(wait.seconds ?? 0, lang) })}
                </p>
              ) : value ? (
                <>
                  <TaskDurationFields elementId={`wait-${wait.element_id}`} taskName={wait.name} task={value}
                    onChange={(next) => set(wait.element_id, next)} />
                  <Button type="button" size="sm" variant="ghost" className="h-7 w-fit px-2 text-xs"
                    aria-label={t("simulation.config.waits.remove", { name: wait.name })}
                    onClick={() => set(wait.element_id, undefined)}>
                    {t("simulation.config.waits.removeShort")}
                  </Button>
                </>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">{t("simulation.config.waits.unset")}</p>
                  <Button type="button" size="sm" variant="outline" className="h-7 px-2 text-xs"
                    aria-label={t("simulation.config.waits.set", { name: wait.name })}
                    onClick={() => set(wait.element_id, NEW_WAIT)}>
                    {t("simulation.config.waits.setShort")}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
