import React from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { Input } from "@/ui/input";

import { ConditionGroups } from "./GatewayRulesEditor";
import { defaultRule, type BranchRuleDraft, type CaseAttributeDraft } from "./caseRules";
import { MAX_REPEATS, reworkIssue, skipIssue, type FlowRuleIssue } from "./flowRules";
import type { TaskDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * SIM-35: una quota dei casi salta l'attività, o finita torna indietro a rifare
 * il lavoro. Entrambi possono valere solo per i casi che soddisfano una regola.
 */
export function FlowRules({
  elementId,
  taskName,
  task,
  activities,
  attributes,
  onChange,
}: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  /** Le attività del processo, nell'ordine del pannello: fra queste si sceglie da dove ripartire. */
  activities: { element_id: string; name: string }[];
  attributes: CaseAttributeDraft[];
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const activityIds = new Set(activities.map((a) => a.element_id));
  const skipProblem = task.skip ? skipIssue(task.skip, attributes) : null;
  const reworkProblem = task.rework ? reworkIssue(task.rework, attributes, activityIds) : null;
  const number = (raw: string) => (raw === "" ? Number.NaN : Number(raw));

  return (
    <div className="sim-task-flow-rules mt-3 grid gap-3 border-t border-border pt-3" data-flow-rules={elementId}>
      <fieldset className="grid gap-2">
        <legend className="sr-only">{t("simulation.config.skip.legend", { task: taskName })}</legend>
        <label className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Checkbox
            checked={task.skip !== undefined}
            onCheckedChange={(checked) => onChange({ ...task, skip: checked === true ? { percent: 20 } : undefined })}
            aria-label={`${t("simulation.config.skip.toggle")} · ${taskName}`}
          />
          {t("simulation.config.skip.toggle")}
        </label>
        {task.skip && (
          <div className="grid gap-2 rounded-md border border-border bg-card p-2.5">
            <PercentField
              id={`sim-skip-${elementId}`}
              label={t(task.skip.rule ? "simulation.config.skip.percentOfMatching" : "simulation.config.skip.percent")}
              taskName={taskName}
              value={task.skip.percent}
              invalid={skipProblem === "skipPercent"}
              onChange={(percent) => task.skip && onChange({ ...task, skip: { ...task.skip, percent: number(percent) } })}
            />
            <OnlyFor
              id={`skip-${elementId}`}
              subject={`${t("simulation.config.skip.toggle")} · ${taskName}`}
              rule={task.skip.rule}
              attributes={attributes}
              onChange={(rule) => task.skip && onChange({ ...task, skip: { ...task.skip, rule } })}
            />
            <Issue id={`sim-skip-${elementId}`} issue={skipProblem === "rule" ? null : skipProblem} />
          </div>
        )}
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="sr-only">{t("simulation.config.rework.legend", { task: taskName })}</legend>
        <label className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Checkbox
            checked={task.rework !== undefined}
            onCheckedChange={(checked) => onChange({
              ...task,
              rework: checked === true ? { backTo: elementId, percent: 10, maxRepeats: 1 } : undefined,
            })}
            aria-label={`${t("simulation.config.rework.toggle")} · ${taskName}`}
          />
          {t("simulation.config.rework.toggle")}
        </label>
        {task.rework && (
          <div className="grid gap-2 rounded-md border border-border bg-card p-2.5">
            <label className="grid gap-1">
              <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.rework.backTo")}</span>
              <select
                className={NATIVE_SELECT}
                aria-label={`${t("simulation.config.rework.backTo")} · ${taskName}`}
                aria-invalid={reworkProblem === "reworkTarget" || undefined}
                aria-describedby={reworkProblem === "reworkTarget" ? `sim-rework-${elementId}-issue` : undefined}
                value={activityIds.has(task.rework.backTo) ? task.rework.backTo : ""}
                onChange={(e) => task.rework && onChange({ ...task, rework: { ...task.rework, backTo: e.target.value } })}
              >
                {!activityIds.has(task.rework.backTo) && <option value="">{t("simulation.config.rework.chooseTarget")}</option>}
                {activities.map((a) => (
                  <option key={a.element_id} value={a.element_id}>
                    {a.element_id === elementId ? t("simulation.config.rework.self", { task: a.name }) : a.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-xs text-muted-foreground">{t("simulation.config.rework.backToHint")}</p>
            <div className="grid grid-cols-2 items-end gap-2">
              <PercentField
                id={`sim-rework-${elementId}`}
                label={t("simulation.config.rework.percent")}
                taskName={taskName}
                value={task.rework.percent}
                invalid={reworkProblem === "reworkPercent"}
                onChange={(percent) => task.rework && onChange({ ...task, rework: { ...task.rework, percent: number(percent) } })}
              />
              <label className="grid gap-1">
                <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.rework.maxRepeats")}</span>
                <Input
                  className="h-8"
                  type="number"
                  min={1}
                  max={MAX_REPEATS}
                  step={1}
                  aria-label={`${t("simulation.config.rework.maxRepeats")} · ${taskName}`}
                  aria-invalid={reworkProblem === "reworkRepeats" || undefined}
                  aria-describedby={reworkProblem === "reworkRepeats" ? `sim-rework-${elementId}-issue` : undefined}
                  value={Number.isFinite(task.rework.maxRepeats) ? task.rework.maxRepeats : ""}
                  onChange={(e) => task.rework && onChange({ ...task, rework: { ...task.rework, maxRepeats: number(e.target.value) } })}
                />
              </label>
            </div>
            <OnlyFor
              id={`rework-${elementId}`}
              subject={`${t("simulation.config.rework.toggle")} · ${taskName}`}
              rule={task.rework.rule}
              attributes={attributes}
              onChange={(rule) => task.rework && onChange({ ...task, rework: { ...task.rework, rule } })}
            />
            <Issue id={`sim-rework-${elementId}`} issue={reworkProblem === "rule" ? null : reworkProblem} />
          </div>
        )}
      </fieldset>
    </div>
  );
}

function PercentField({ id, label, taskName, value, invalid, onChange }: {
  id: string;
  label: string;
  taskName: string;
  value: number;
  invalid: boolean;
  onChange: (raw: string) => void;
}): React.JSX.Element {
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input
        className="h-8"
        type="number"
        min={0}
        max={100}
        step="any"
        aria-label={`${label} · ${taskName}`}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${id}-issue` : undefined}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** "Solo per i casi che…": una regola facoltativa sugli attributi del caso. */
function OnlyFor({ id, subject, rule, attributes, onChange }: {
  id: string;
  subject: string;
  rule: BranchRuleDraft | undefined;
  attributes: CaseAttributeDraft[];
  onChange: (rule: BranchRuleDraft | undefined) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  if (!rule) {
    return attributes.length === 0
      ? <p className="text-xs text-muted-foreground">{t("simulation.config.flowRuleNoAttributes")}</p>
      : (
        <Button type="button" size="sm" variant="outline" className="h-7 w-fit px-2 text-xs"
          onClick={() => onChange([[defaultRule(attributes)]])}>
          {t("simulation.config.flowRuleOnlyFor")}
        </Button>
      );
  }
  return (
    <ConditionGroups
      id={id}
      legend={t("simulation.config.flowRuleLegend")}
      subject={subject}
      groups={rule}
      attributes={attributes}
      // Senza gruppi la regola non c'e' piu': vale di nuovo per tutti i casi.
      onChange={(groups) => onChange(groups.length ? groups : undefined)}
      sentenceKey="simulation.config.flowRuleReads"
      action={(
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onChange(undefined)}>
          {t("simulation.config.flowRuleAll")}
        </Button>
      )}
    />
  );
}

function Issue({ id, issue }: { id: string; issue: FlowRuleIssue | null }): React.JSX.Element | null {
  const { t } = useTranslation("process");
  if (!issue) return null;
  return <p id={`${id}-issue`} role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.flowRuleIssue.${issue}`)}</p>;
}
