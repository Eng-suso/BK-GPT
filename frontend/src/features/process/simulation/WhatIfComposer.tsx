import React from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { Textarea } from "@/ui/textarea";

import { diffScenario } from "./scenarioPatch";
import { translateWhatIf } from "./simulationApi";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate, WhatIfTranslation } from "./simulationTypes";
import { useScenarioChanges } from "./useScenarioChanges";
import { readError } from "./useScenarioLab";
import { applyWhatIf, whatIfContext } from "./whatIf";

type Props = {
  bpmnModelId: string;
  template: ScenarioTemplate | null;
  draft: ScenarioDraft;
  onApply: (next: ScenarioDraft) => void;
};

/**
 * SIM-23: una frase del consulente diventa un'anteprima delle modifiche della
 * bozza. Il modello traduce soltanto; l'anteprima si legge come le modifiche di
 * uno scenario del workspace, e la bozza cambia solo con "Applica". Nessun run
 * parte da qui: lo avvia il consulente, come sempre.
 */
export function WhatIfComposer({ bpmnModelId, template, draft, onApply }: Props): React.JSX.Element {
  const { t } = useTranslation("process");
  const [sentence, setSentence] = React.useState("");
  const [result, setResult] = React.useState<WhatIfTranslation | null>(null);
  const [applied, setApplied] = React.useState(false);
  const changes = useScenarioChanges(draft, template);
  const fieldId = React.useId();
  const hintId = `${fieldId}-hint`;

  const translation = useMutation({
    mutationFn: (text: string) => {
      const names = Object.fromEntries((template?.tasks ?? []).map((task) => [task.element_id, task.name]));
      return translateWhatIf(bpmnModelId, { sentence: text, ...whatIfContext(draft, names) });
    },
    onSuccess: (data) => setResult(data),
  });

  // L'anteprima si calcola sulla bozza di adesso: se nel frattempo cambia, si vede cambiare.
  const preview = React.useMemo(() => (result ? applyWhatIf(draft, result.changes) : null), [draft, result]);
  const patch = React.useMemo(() => (preview ? diffScenario(draft, preview.draft) : []), [draft, preview]);
  const lines = React.useMemo(() => changes.readPatch(patch).map((change) => changes.text(change)), [changes, patch]);

  const trimmed = sentence.trim();
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmed || translation.isPending) return;
    setApplied(false);
    setResult(null);
    translation.mutate(trimmed);
  };
  const apply = () => {
    if (!preview || patch.length === 0) return;
    onApply(preview.draft);
    setResult(null);
    setApplied(true);
  };
  const discard = () => {
    setResult(null);
    translation.reset();
  };

  return (
    <section aria-labelledby={`${fieldId}-title`} className="grid gap-3 border-b border-border py-4" data-testid="sim-what-if">
      <div className="grid gap-1">
        <h4 id={`${fieldId}-title`} className="text-sm font-semibold text-foreground">{t("simulation.whatIf.title")}</h4>
        <p id={hintId} className="text-xs text-muted-foreground">{t("simulation.whatIf.hint")}</p>
      </div>
      <form className="grid gap-2" onSubmit={submit}>
        <label htmlFor={fieldId} className="sr-only">{t("simulation.whatIf.label")}</label>
        <Textarea
          id={fieldId}
          aria-describedby={hintId}
          rows={2}
          maxLength={400}
          value={sentence}
          placeholder={t("simulation.whatIf.placeholder")}
          onChange={(event) => setSentence(event.target.value)}
          onKeyDown={(event) => {
            // Invio traduce, Maiusc+Invio va a capo: come la chat.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" size="sm" disabled={!trimmed || translation.isPending}>
            {translation.isPending ? t("simulation.whatIf.translating") : t("simulation.whatIf.translate")}
          </Button>
          <span role="status" className="text-xs text-muted-foreground">
            {applied ? t("simulation.whatIf.applied") : ""}
          </span>
        </div>
      </form>

      {translation.isError && (
        <p role="alert" className="text-sm text-destructive">{readError(translation.error)}</p>
      )}

      {result && preview && (
        <div className="grid gap-2 rounded-lg border border-border bg-muted/40 p-3" aria-live="polite">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("simulation.whatIf.previewTitle")}</p>
          {lines.length > 0 ? (
            <ul className="grid gap-1 text-sm text-foreground">
              {lines.map((line, index) => <li key={index}>{line}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("simulation.whatIf.nothing")}</p>
          )}
          {result.not_understood && (
            <p className="text-sm text-muted-foreground">{t("simulation.whatIf.notUnderstood", { text: result.not_understood })}</p>
          )}
          {result.rejected + preview.skipped.length > 0 && (
            <p className="text-sm text-muted-foreground">{t("simulation.whatIf.rejected", { count: result.rejected + preview.skipped.length })}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" disabled={patch.length === 0} onClick={apply}>{t("simulation.whatIf.apply")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={discard}>{t("simulation.whatIf.discard")}</Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("simulation.whatIf.noRun")}</p>
        </div>
      )}
    </section>
  );
}
