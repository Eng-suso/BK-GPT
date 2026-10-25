import React from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";

import { writeSimulationNarrative } from "./simulationApi";
import type { SimulationNarrativeRequest } from "./simulationTypes";
import { readError } from "./useScenarioLab";

type Props = {
  bpmnModelId: string;
  /** Il nome dell'alternativa, per dire di quale testo si parla. */
  name: string;
  request: SimulationNarrativeRequest;
  text: string | null;
  onWritten: (text: string) => void;
};

/**
 * SIM-24b: la lettura calcolata di un'alternativa, riscritta per il cliente su
 * richiesta del consulente. La lettura calcolata resta accanto: se il modello
 * non risponde, o scrive un numero suo, il backend rifiuta e lo si dice.
 */
export function ClientNarrative({ bpmnModelId, name, request, text, onWritten }: Props): React.JSX.Element {
  const { t } = useTranslation("process");
  const writing = useMutation({
    mutationFn: () => writeSimulationNarrative(bpmnModelId, request),
    onSuccess: (result) => onWritten(result.text),
  });

  return (
    <div className="mt-1.5 grid gap-1.5" data-sim-client-narrative>
      {text && (
        <figure className="grid gap-1 rounded-md border border-border bg-muted/40 px-3 py-2" aria-label={t("simulation.narrative.label", { name })}>
          <blockquote className="text-sm leading-relaxed text-foreground">{text}</blockquote>
          <figcaption className="text-xs text-muted-foreground">{t("simulation.narrative.source")}</figcaption>
        </figure>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={writing.isPending}
          aria-label={`${text ? t("simulation.narrative.rewrite") : t("simulation.narrative.write")} · ${name}`}
          onClick={() => writing.mutate()}
        >
          {writing.isPending ? t("simulation.narrative.writing") : text ? t("simulation.narrative.rewrite") : t("simulation.narrative.write")}
        </Button>
      </div>
      {writing.isError && <p role="alert" className="text-xs text-destructive">{readError(writing.error)}</p>}
    </div>
  );
}
