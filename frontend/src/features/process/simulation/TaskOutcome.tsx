import React from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/ui/checkbox";
import { Input } from "@/ui/input";

import { CategoryFields } from "./CaseAttributesSection";
import type { CaseAttributeDraft } from "./caseRules";
import type { TaskDraft } from "./simulationScenario";
import { defaultOutcome, outcomeAttributeId, outcomeIssue } from "./taskOutcome";

/**
 * SIM-31b: finita l'attività, il caso riceve un esito ("OK 80%, KO 20%") che
 * le decisioni, i salti e le rilavorazioni a valle leggono nelle loro regole.
 */
export function TaskOutcome({ elementId, taskName, task, attributes, outcomes, onChange }: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  /** Gli attributi del caso: l'esito non può prenderne il nome. */
  attributes: CaseAttributeDraft[];
  /** Gli esiti di tutte le attività, come attributi delle regole. */
  outcomes: CaseAttributeDraft[];
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const outcome = task.outcome;
  const issue = outcome ? outcomeIssue(elementId, outcome, attributes, outcomes) : null;
  const issueId = `sim-outcome-${elementId}-issue`;

  return (
    <fieldset className="sim-task-outcome mt-3 grid gap-2 border-t border-border pt-3" data-outcome={elementId}>
      <legend className="sr-only">{t("simulation.config.outcome.legend", { task: taskName })}</legend>
      <label className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Checkbox
          checked={outcome !== undefined}
          onCheckedChange={(checked) => {
            const next = { ...task };
            if (checked === true) next.outcome = defaultOutcome();
            else delete next.outcome;
            onChange(next);
          }}
          aria-label={`${t("simulation.config.outcome.toggle")} · ${taskName}`}
        />
        {t("simulation.config.outcome.toggle")}
      </label>
      {outcome && (
        <div className="grid gap-2 rounded-md border border-border bg-card p-2.5">
          <label className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.outcome.name")}</span>
            <Input
              className="h-8"
              value={outcome.name}
              maxLength={64}
              aria-label={`${t("simulation.config.outcome.name")} · ${taskName}`}
              aria-invalid={issue === "name" || issue === "duplicateName" || issue === "reservedName" ? true : undefined}
              aria-describedby={issue ? issueId : undefined}
              onChange={(e) => onChange({ ...task, outcome: { ...outcome, name: e.target.value } })}
            />
          </label>
          <CategoryFields
            attribute={{ id: outcomeAttributeId(elementId), name: outcome.name, kind: "category", categories: outcome.categories }}
            invalid={issue}
            describedBy={issue ? issueId : undefined}
            onChange={(next) => onChange({ ...task, outcome: { ...outcome, categories: next.categories } })}
          />
          <p className="text-xs text-muted-foreground">{t("simulation.config.outcome.hint")}</p>
          {issue && (
            <p id={issueId} role="alert" className="text-xs font-medium text-destructive">
              {t(`simulation.config.outcome.issue.${issue}`)}
            </p>
          )}
        </div>
      )}
    </fieldset>
  );
}
