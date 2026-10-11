import React from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/ui/input";

import { DISTRIBUTIONS, type DistributionName } from "./simulationTypes";
import { DISTRIBUTION_PARAMETERS, taskDurationIssue, type DurationDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * La durata di un'attività: distribuzione e i parametri che quella distribuzione usa.
 * I campi facoltativi vuoti restano vuoti: le ipotesi standard le applica il backend.
 * Serve sia per il ruolo principale sia per ogni altro ruolo dell'attività.
 */
export function TaskDurationFields<T extends DurationDraft>({
  elementId,
  taskName,
  task,
  onChange,
  kind = "duration",
}: {
  elementId: string;
  taskName: string;
  task: T;
  onChange: (next: T) => void;
  /** ``arrival``: il tempo fra due arrivi dei casi, con le sue etichette (A2-3). */
  kind?: "duration" | "arrival";
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const parameters = DISTRIBUTION_PARAMETERS[task.distribution];
  const issue = taskDurationIssue(task);
  const issueId = `sim-duration-issue-${elementId}`;
  const meanLabel = t(kind === "arrival" ? "simulation.config.arrivalMeanMin" : "simulation.config.durationMin");
  const hint = task.distribution === "uniform"
    ? kind === "arrival" ? "simulation.config.arrivalUniformHint" : "simulation.config.uniformHint"
    : task.distribution === "expon"
      ? "simulation.config.exponDefaults"
      : parameters.std ? "simulation.config.durationDefaults" : null;

  const optional = (field: "stdMinutes" | "minMinutes" | "maxMinutes", label: string) => (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input
        className="h-8"
        type="number"
        min={0}
        step="any"
        aria-label={`${label} · ${taskName}`}
        aria-invalid={issue !== null && field !== "stdMinutes" ? true : undefined}
        aria-describedby={issue !== null && field !== "stdMinutes" ? issueId : undefined}
        value={task[field] ?? ""}
        onChange={(e) => onChange({ ...task, [field]: e.target.value === "" ? undefined : Number(e.target.value) })}
      />
    </label>
  );

  return (
    <div className="grid gap-2">
      <div className="sim-task-timing grid grid-cols-[minmax(90px,0.7fr)_minmax(0,1fr)] gap-3">
        {parameters.mean ? (
          <label className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">{meanLabel}</span>
            <Input
              className="h-8"
              type="number"
              min={1}
              aria-label={`${meanLabel} · ${taskName}`}
              value={task.meanMinutes}
              onChange={(e) => onChange({ ...task, meanMinutes: e.target.value === "" ? 0 : Number(e.target.value) })}
            />
          </label>
        ) : <span aria-hidden />}
        <label className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.distribution")}</span>
          <select
            className={NATIVE_SELECT}
            aria-label={`${t("simulation.config.distribution")} · ${taskName}`}
            value={task.distribution}
            onChange={(e) => onChange({ ...task, distribution: e.target.value as DistributionName })}
          >
            {DISTRIBUTIONS.map((d) => (
              <option key={d} value={d}>{t(`simulation.config.dist.${d}`)}</option>
            ))}
          </select>
        </label>
      </div>
      {(parameters.std || parameters.bounds) && (
        <div className="grid grid-cols-3 gap-2">
          {parameters.std && optional("stdMinutes", t("simulation.config.stdMin"))}
          {parameters.bounds && optional("minMinutes", t("simulation.config.minMin"))}
          {parameters.bounds && optional("maxMinutes", t("simulation.config.maxMin"))}
        </div>
      )}
      {issue ? (
        <p id={issueId} role="alert" className="text-xs font-medium text-destructive">
          {t(`simulation.config.durationIssue.${issue}`)}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{t(hint)}</p>
      ) : null}
    </div>
  );
}
