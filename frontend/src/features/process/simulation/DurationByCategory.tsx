import React from "react";
import { useTranslation } from "react-i18next";

import { TaskDurationFields } from "./TaskDurationFields";
import type { CaseAttributeDraft } from "./caseRules";
import { durationOf, type DurationDraft, type TaskDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * SIM-32: la durata dell'attivita' cambia con un attributo a categorie del caso.
 * Ogni categoria parte dalla durata di base; i casi di altre categorie la usano.
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
  const categorical = attributes.filter((a): a is Extract<CaseAttributeDraft, { kind: "category" }> => a.kind === "category");
  if (categorical.length === 0 && !task.durationBy) return null;
  const attribute = categorical.find((a) => a.id === task.durationBy?.attributeId);
  const variant = (value: string): DurationDraft => task.durationBy?.variants[value] ?? durationOf(task);
  const setVariant = (value: string, next: DurationDraft) => task.durationBy && onChange({
    ...task,
    durationBy: { ...task.durationBy, variants: { ...task.durationBy.variants, [value]: next } },
  });

  return (
    <div className="sim-task-duration-by mt-3 grid gap-2 border-t border-border pt-3" data-duration-by={elementId}>
      <label className="grid gap-1">
        <span className="text-xs font-medium text-foreground">{t("simulation.config.durationBy")}</span>
        <select
          className={NATIVE_SELECT}
          aria-label={`${t("simulation.config.durationBy")} · ${taskName}`}
          value={attribute?.id ?? ""}
          onChange={(e) => onChange({ ...task, durationBy: e.target.value ? { attributeId: e.target.value, variants: {} } : undefined })}
        >
          <option value="">{t("simulation.config.durationBySame")}</option>
          {categorical.map((a) => <option key={a.id} value={a.id}>{a.name || t("simulation.config.unnamedAttribute")}</option>)}
        </select>
      </label>
      {task.durationBy && !attribute && <p role="alert" className="text-xs font-medium text-destructive">{t("simulation.config.durationByMissing")}</p>}
      {attribute && (
        <>
          <p className="text-xs text-muted-foreground">{t("simulation.config.durationByHint", { attribute: attribute.name })}</p>
          <ul className="grid gap-2">
            {attribute.categories.filter((c) => c.value.trim()).map((category) => (
              <li key={category.value} className="grid gap-1.5 rounded-md border border-border bg-card p-2.5">
                <p className="text-xs font-medium text-foreground">{t("simulation.config.durationByCategory", { attribute: attribute.name, value: category.value })}</p>
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
    </div>
  );
}
