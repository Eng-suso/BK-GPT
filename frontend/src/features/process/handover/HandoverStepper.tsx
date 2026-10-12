import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import type { HandoverStage } from "./handoverModel";

const ORDER: HandoverStage[] = ["design", "review", "approved"];

/**
 * Dove si trova il processo: preparazione, con il cliente, in uso. Non e' una
 * navigazione: tre tappe che si leggono in un colpo d'occhio, con quella
 * attuale evidenziata e quelle fatte spuntate.
 */
export function HandoverStepper({ stage }: { stage: HandoverStage }): React.JSX.Element {
  const { t } = useTranslation("process");
  const current = ORDER.indexOf(stage);
  return (
    <ol className="handover-stepper" aria-label={t("handover.stepper.label")}>
      {ORDER.map((step, index) => {
        const state = index < current ? "done" : index === current ? "current" : "next";
        return (
          <li key={step} data-state={state} aria-current={state === "current" ? "step" : undefined}>
            <span className="handover-stepper-marker" aria-hidden>{state === "done" ? <Check className="size-3.5" /> : index + 1}</span>
            <span className="handover-stepper-label">
              {t(`handover.stepper.${step}`)}
              {state !== "next" && <span className="sr-only"> · {t(state === "done" ? "handover.stepper.done" : "handover.stepper.current")}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
