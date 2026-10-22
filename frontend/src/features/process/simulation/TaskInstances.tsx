import React from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/ui/input";

import { MAX_INSTANCES, instancesIssue } from "./instances";
import type { TaskDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

type TemplateTask = ScenarioTemplate["tasks"][number];

/**
 * SIM-11f/h: le istanze per caso di un'attività multi-istanza. Un numero fisso
 * del BPMN si legge e basta; su una collezione il BPMN non dice quante, e le
 * imposta il consulente. Senza, l'attività si esegue una volta.
 */
export function TaskInstances({ task, cfg, onChange }: {
  task: TemplateTask;
  cfg: TaskDraft;
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element | null {
  const { t } = useTranslation("process");
  if (!task.multi_instance) return null;
  const mode = t(`simulation.config.instances.${task.multi_instance}`);
  if (task.instances != null) {
    return (
      <p className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground" data-instances={task.element_id}>
        {t("simulation.config.instances.fixed", { count: task.instances, mode })}
      </p>
    );
  }
  const issue = instancesIssue(cfg.instances);
  const issueId = `sim-instances-${task.element_id}-issue`;
  return (
    <div className="mt-3 grid gap-1 border-t border-border pt-3" data-instances={task.element_id}>
      <label className="grid gap-1">
        <span className="text-xs font-medium text-foreground">{t("simulation.config.instances.label")}</span>
        <Input
          className="h-8 w-24"
          type="number"
          min={1}
          max={MAX_INSTANCES}
          step={1}
          inputMode="numeric"
          aria-label={`${t("simulation.config.instances.label")} · ${task.name}`}
          aria-invalid={issue ? true : undefined}
          aria-describedby={issue ? issueId : undefined}
          value={cfg.instances ?? ""}
          onChange={(e) => onChange({ ...cfg, instances: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
      </label>
      <p className="text-xs text-muted-foreground">{t("simulation.config.instances.hint", { mode })}</p>
      {issue && (
        <p id={issueId} role="alert" className="text-xs font-medium text-destructive">
          {t("simulation.config.instances.issue", { max: MAX_INSTANCES })}
        </p>
      )}
    </div>
  );
}
