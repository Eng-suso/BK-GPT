import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { TaskDurationFields } from "./TaskDurationFields";
import type { CaseAttributeDraft } from "./caseRules";
import { durationOf, thresholdsValid, type DurationDraft, type TaskDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * SIM-32: la durata dell'attivita' cambia con un attributo del caso. A
 * categorie, ogni categoria ha la sua durata; numerico (SIM-32b), soglie
 * crescenti "fino a". Ogni variante parte dalla durata di base; gli altri casi
 * la usano.
 */
export function DurationByCategory({
  elementId,
  taskName,
  task,
  attributes,
  onChange,
}: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  attributes: CaseAttributeDraft[];
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element | null {
  const { t } = useTranslation("process");
  if (attributes.length === 0 && !task.durationBy) return null;
  const attribute = attributes.find((a) => a.id === task.durationBy?.attributeId);
  const attributeName = attribute?.name.trim() || t("simulation.config.unnamedAttribute");
  const variant = (value: string): DurationDraft => task.durationBy?.variants[value] ?? durationOf(task);
  const setVariant = (value: string, next: DurationDraft) => task.durationBy && onChange({
    ...task,
    durationBy: { ...task.durationBy, variants: { ...task.durationBy.variants, [value]: next } },
  });
  const thresholds = task.durationBy?.thresholds ?? [];
  const setThresholds = (next: { upTo: number; duration: DurationDraft }[]) => task.durationBy && onChange({
    ...task,
    durationBy: { ...task.durationBy, thresholds: next },
  });
  const choose = (id: string) => {
    const next = attributes.find((a) => a.id === id);
    if (!next) return onChange({ ...task, durationBy: undefined });
    onChange({
      ...task,
      durationBy: next.kind === "number"
        // Una prima soglia a metà dell'intervallo: un punto di partenza, non un dato.
        ? { attributeId: id, variants: {}, thresholds: [{ upTo: Math.round((next.minimum + next.maximum) / 2), duration: durationOf(task) }] }
        : { attributeId: id, variants: {} },
    });
  };

  return (
    <div className="sim-task-duration-by mt-3 grid gap-2 border-t border-border pt-3" data-duration-by={elementId}>
      <label className="grid gap-1">
        <span className="text-xs font-medium text-foreground">{t("simulation.config.durationBy")}</span>
        <select
          className={NATIVE_SELECT}
          aria-label={`${t("simulation.config.durationBy")} · ${taskName}`}
          value={attribute?.id ?? ""}
          onChange={(e) => choose(e.target.value)}
        >
          <option value="">{t("simulation.config.durationBySame")}</option>
          {attributes.map((a) => <option key={a.id} value={a.id}>{a.name || t("simulation.config.unnamedAttribute")}</option>)}
        </select>
      </label>
      {task.durationBy && !attribute && <p role="alert" className="text-xs font-medium text-destructive">{t("simulation.config.durationByMissing")}</p>}
      {attribute?.kind === "category" && (
        <>
          <p className="text-xs text-muted-foreground">{t("simulation.config.durationByHint", { attribute: attributeName })}</p>
          <ul className="grid gap-2">
            {attribute.categories.filter((c) => c.value.trim()).map((category) => (
              <li key={category.value} className="grid gap-1.5 rounded-md border border-border bg-card p-2.5">
                <p className="text-xs font-medium text-foreground">{t("simulation.config.durationByCategory", { attribute: attributeName, value: category.value })}</p>
                <TaskDurationFields
                  elementId={`${elementId}-${category.value}`}
                  taskName={`${taskName} · ${category.value}`}
                  task={variant(category.value)}
                  onChange={(next) => setVariant(category.value, next)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
      {attribute?.kind === "number" && (
        <>
          <p className="text-xs text-muted-foreground">{t("simulation.config.durationByThresholdHint", { attribute: attributeName })}</p>
          <ul className="grid gap-2">
            {thresholds.map((threshold, index) => {
              const label = `${taskName} · ${t("simulation.config.durationByUpTo", { attribute: attributeName, value: Number.isFinite(threshold.upTo) ? threshold.upTo : "…" })}`;
              return (
                <li key={index} className="grid gap-1.5 rounded-md border border-border bg-card p-2.5" data-threshold={index + 1}>
                  <div className="flex items-end gap-2">
                    <label className="grid min-w-0 flex-1 gap-1">
                      <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.durationByUpToLabel", { attribute: attributeName })}</span>
                      <Input
                        className="h-8"
                        type="number"
                        step="any"
                        aria-label={`${t("simulation.config.durationByUpToLabel", { attribute: attributeName })} · ${taskName} · ${index + 1}`}
                        aria-invalid={!thresholdsValid(thresholds) || undefined}
                        value={Number.isFinite(threshold.upTo) ? threshold.upTo : ""}
                        onChange={(e) => setThresholds(thresholds.map((th, i) => (i === index ? { ...th, upTo: e.target.value === "" ? Number.NaN : Number(e.target.value) } : th)))}
                      />
                    </label>
                    <Button type="button" size="icon" variant="ghost"
                      aria-label={t("simulation.config.durationByRemoveThreshold", { n: index + 1, task: taskName })}
                      onClick={() => (thresholds.length > 1 ? setThresholds(thresholds.filter((_, i) => i !== index)) : choose(""))}>
                      <X aria-hidden className="size-4" />
                    </Button>
                  </div>
                  <TaskDurationFields
                    elementId={`${elementId}-threshold-${index}`}
                    taskName={label}
                    task={threshold.duration}
                    onChange={(next) => setThresholds(thresholds.map((th, i) => (i === index ? { ...th, duration: next } : th)))}
                  />
                </li>
              );
            })}
          </ul>
          <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
            disabled={thresholds.length >= 20}
            onClick={() => {
              const last = thresholds[thresholds.length - 1];
              const upTo = last && Number.isFinite(last.upTo) ? last.upTo * 2 : attribute.maximum;
              setThresholds([...thresholds, { upTo, duration: durationOf(task) }]);
            }}>
            <Plus aria-hidden className="size-3.5" />
            {t("simulation.config.durationByAddThreshold")}
          </Button>
          {!thresholdsValid(thresholds)
            ? <p role="alert" className="text-xs font-medium text-destructive">{t("simulation.config.durationByThresholdIssue")}</p>
            : <p className="text-xs text-muted-foreground">{t("simulation.config.durationByOthersNumber", { attribute: attributeName, value: thresholds[thresholds.length - 1].upTo })}</p>}
        </>
      )}
    </div>
  );
}
