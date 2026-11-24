import React from "react";
import { useTranslation } from "react-i18next";

import { InlineNotice } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { formatDuration } from "./simulationResults";
import { DISTRIBUTIONS, type DistributionName } from "./simulationTypes";
import { DISTRIBUTION_PARAMETERS, arrivalsRunFaster, taskDurationIssue, type DurationDraft } from "./simulationScenario";

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
  const { t, i18n } = useTranslation("process");
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const parameters = DISTRIBUTION_PARAMETERS[task.distribution];
  const issue = taskDurationIssue(task);
  const issueId = `sim-duration-issue-${elementId}`;
  const explanationId = `sim-duration-explanation-${elementId}`;
  const isArrival = kind === "arrival";
  const faster = isArrival && issue === null ? arrivalsRunFaster(task) : null;
  const lang = i18n.language?.startsWith("en") ? "en" : "it";
  // Al minuto, come le altre durate del pannello: "21 min", non "20 min 40 s".
  const readable = (seconds: number) => formatDuration(seconds >= 60 ? Math.round(seconds / 60) * 60 : seconds, lang);
  const interpretation = task.distribution === "uniform"
    ? t(isArrival ? "simulation.config.durationGuide.uniformArrival" : "simulation.config.durationGuide.uniformTask", { min: task.minMinutes ?? "—", max: task.maxMinutes ?? "—" })
    : t(`simulation.config.durationGuide.${task.distribution}${isArrival ? "Arrival" : "Task"}`, { mean: task.meanMinutes });
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
      {isArrival && <div className="grid gap-0.5"><strong className="text-sm text-foreground">{t("simulation.config.durationGuide.arrivalTitle")}</strong><span className="text-xs text-muted-foreground">Inter-arrival time</span></div>}
      <div className="sim-task-timing grid grid-cols-[minmax(90px,0.7fr)_minmax(0,1fr)] gap-3">
        {parameters.mean ? (
          <label className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">{meanLabel}</span>
            <Input
              className="h-8"
              type="number"
              min={1}
              aria-label={`${meanLabel} · ${taskName}`}
              aria-describedby={explanationId}
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
            aria-describedby={explanationId}
            value={task.distribution}
            onChange={(e) => onChange({ ...task, distribution: e.target.value as DistributionName })}
          >
            {DISTRIBUTIONS.map((d) => (
              <option key={d} value={d}>{t(`simulation.config.dist.${d}`)}</option>
            ))}
          </select>
        </label>
      </div>
      {task.distribution === "uniform" && <div className="grid grid-cols-2 gap-2">
        {optional("minMinutes", t("simulation.config.minMin"))}
        {optional("maxMinutes", t("simulation.config.maxMin"))}
      </div>}
      <p id={explanationId} className="text-xs leading-relaxed text-muted-foreground">{interpretation}</p>
      {faster && task.maxMinutes !== undefined && (
        <InlineNotice
          tone="warning"
          title={t("simulation.config.arrivalsFaster.title")}
          action={(
            <Button type="button" size="sm" variant="outline" onClick={() => onChange({ ...task, maxMinutes: faster.suggestedMaxMinutes })}>
              {t("simulation.config.arrivalsFaster.action", { suggested: readable(faster.suggestedMaxMinutes * 60) })}
            </Button>
          )}
        >
          {t("simulation.config.arrivalsFaster.body", {
            max: readable(task.maxMinutes * 60),
            produced: readable(faster.producedSeconds),
            mean: readable(task.meanMinutes * 60),
            more: faster.morePercent,
          })}
        </InlineNotice>
      )}
      <details className="sim-duration-details rounded-md border border-border px-3 py-2" open={advancedOpen || issue !== null} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
          <summary className="cursor-pointer text-xs font-medium text-foreground">{t("simulation.config.durationGuide.technicalDetails")}</summary>
          {task.distribution !== "fixed" && task.distribution !== "uniform" && <>
          <p className="mt-2 text-xs text-muted-foreground">{t("simulation.config.durationGuide.technicalHint")}</p>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {parameters.std && optional("stdMinutes", t("simulation.config.stdMin"))}
            {parameters.bounds && optional("minMinutes", t("simulation.config.minMin"))}
            {parameters.bounds && optional("maxMinutes", t("simulation.config.maxMin"))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{t("simulation.config.durationGuide.boundsHint")}</p>
          {hint && <p className="mt-2 text-xs text-muted-foreground">{t(hint)}</p>}
          </>}
          <p className="mt-2 text-xs text-muted-foreground">{t("simulation.config.durationGuide.technicalDistribution")}: <code>{task.distribution}</code> · {t("simulation.config.durationGuide.technicalUnit")}</p>
          <p className="mt-2 break-all text-xs text-muted-foreground">{t(isArrival ? "simulation.config.durationGuide.arrivalKey" : "simulation.config.durationGuide.modelId")}: <code>{elementId}</code></p>
        </details>
      {issue ? (
        <p id={issueId} role="alert" className="text-xs font-medium text-destructive">
          {t(`simulation.config.durationIssue.${issue}`)}
        </p>
      ) : hint && task.distribution === "uniform" ? (
        <p className="text-xs text-muted-foreground">{t(hint)}</p>
      ) : null}
    </div>
  );
}
