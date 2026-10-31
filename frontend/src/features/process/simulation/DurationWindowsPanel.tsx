import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { Input } from "@/ui/input";

import { Clock, Day } from "./ArrivalBandsPanel";
import { MAX_PERCENT, MAX_WINDOWS, MIN_PERCENT, durationWindowIssues, newDurationWindow, type DurationWindowDraft } from "./durationWindows";
import type { TaskDraft } from "./simulationScenario";

/**
 * SIM-33b: la durata dell'attività cambia con l'ora in cui inizia. Ogni fascia
 * ha la sua variazione in percentuale; fuori dalle fasce vale la durata di base.
 */
export function DurationWindows({ elementId, taskName, task, onChange }: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const windows = task.durationWindows;
  const list = windows ?? [];
  const issues = durationWindowIssues(list);
  const set = (next: DurationWindowDraft[] | undefined) => onChange({ ...task, durationWindows: next });
  const update = (index: number, fields: Partial<DurationWindowDraft>) =>
    set(list.map((window, i) => (i === index ? { ...window, ...fields } : window)));

  return (
    <div className="sim-task-duration-windows mt-3 grid gap-2 border-t border-border pt-3" data-duration-windows={elementId}>
      <label className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Checkbox
          checked={windows !== undefined}
          aria-label={`${t("simulation.config.durationWindows.toggle")} · ${taskName}`}
          onCheckedChange={(checked) => set(checked === true ? [newDurationWindow([])] : undefined)}
        />
        {t("simulation.config.durationWindows.toggle")}
      </label>
      {windows !== undefined && (
        <>
          <p className="text-xs text-muted-foreground">{t("simulation.config.durationWindows.hint")}</p>
          <ul className="grid gap-2">
            {list.map((window, index) => {
              const label = `${t("simulation.config.durationWindows.window", { n: index + 1 })} · ${taskName}`;
              const issue = issues[index];
              const issueId = `sim-duration-window-${elementId}-${index}-issue`;
              return (
                <li key={index} className="grid gap-2 rounded-md border border-border bg-card p-2.5" data-duration-window={index + 1}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">{t("simulation.config.durationWindows.window", { n: index + 1 })}</p>
                    <Button type="button" size="icon" variant="ghost"
                      aria-label={t("simulation.config.durationWindows.remove", { window: label })}
                      onClick={() => set(list.length > 1 ? list.filter((_, i) => i !== index) : undefined)}>
                      <X aria-hidden className="size-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Day label={`${t("simulation.config.fromDay")} · ${label}`} text={t("simulation.config.fromDay")}
                      value={window.fromDay} onChange={(fromDay) => update(index, { fromDay })} />
                    <Day label={`${t("simulation.config.toDay")} · ${label}`} text={t("simulation.config.toDay")}
                      value={window.toDay} onChange={(toDay) => update(index, { toDay })} />
                    <Clock label={`${t("simulation.config.begin")} · ${label}`} text={t("simulation.config.begin")}
                      value={window.begin} invalid={issue === "order" || issue === "overlap"} describedBy={issue ? issueId : undefined}
                      onChange={(begin) => update(index, { begin })} />
                    <Clock label={`${t("simulation.config.end")} · ${label}`} text={t("simulation.config.end")}
                      value={window.end} invalid={issue === "order" || issue === "overlap"} describedBy={issue ? issueId : undefined}
                      onChange={(end) => update(index, { end })} />
                  </div>
                  <label className="grid gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.durationWindows.percent")}</span>
                    <Input
                      className="h-8"
                      type="number"
                      min={MIN_PERCENT}
                      max={MAX_PERCENT}
                      step="any"
                      aria-label={`${t("simulation.config.durationWindows.percent")} · ${label}`}
                      aria-invalid={issue === "percent" || undefined}
                      aria-describedby={issue ? issueId : undefined}
                      value={Number.isFinite(window.percent) ? window.percent : ""}
                      onChange={(e) => update(index, { percent: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
                    />
                  </label>
                  {issue && (
                    <p id={issueId} role="alert" className="text-xs font-medium text-destructive">
                      {t(`simulation.config.durationWindows.issue.${issue}`, { min: MIN_PERCENT, max: MAX_PERCENT })}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
          <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
            disabled={list.length >= MAX_WINDOWS}
            onClick={() => set([...list, newDurationWindow(list)])}>
            <Plus aria-hidden className="size-3.5" />
            {t("simulation.config.durationWindows.add")}
          </Button>
        </>
      )}
    </div>
  );
}
