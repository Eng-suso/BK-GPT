import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/ui/select";

import { TaskDurationFields } from "./TaskDurationFields";
import { newOtherAssignment, roleLabel, type AssignmentDraft, type ResourceDraft, type TaskDraft } from "./simulationScenario";

/**
 * Gli altri ruoli che possono svolgere un'attività (A2-2), ognuno con la sua durata.
 * Il motore dà ogni caso al primo ruolo libero fra il principale e questi.
 */
export function OtherAssignments({
  elementId,
  taskName,
  task,
  resources,
  onChange,
}: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  resources: ResourceDraft[];
  onChange: (next: TaskDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const others = task.otherAssignments ?? [];
  const candidate = newOtherAssignment(task, resources);
  const headingId = `sim-other-roles-${elementId}`;
  const nameOf = (resourceId: string) => {
    const resource = resources.find((r) => r.id === resourceId);
    return resource ? roleLabel(resource) : resourceId;
  };
  const update = (index: number, next: AssignmentDraft) =>
    onChange({ ...task, otherAssignments: others.map((a, i) => (i === index ? next : a)) });

  return (
    <div className="sim-task-others mt-3 grid gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p id={headingId} className="text-xs font-medium text-foreground">{t("simulation.config.otherRoles")}</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-xs"
          aria-label={t("simulation.config.addOtherRoleFor", { task: taskName })}
          disabled={!candidate}
          onClick={() => candidate && onChange({ ...task, otherAssignments: [...others, candidate] })}
        >
          <Plus aria-hidden className="size-3.5" />
          {t("simulation.config.addOtherRole")}
        </Button>
      </div>
      {others.length > 0 ? (
        <p className="text-xs text-muted-foreground">{t("simulation.config.otherRolesHint")}</p>
      ) : !candidate ? (
        <p className="text-xs text-muted-foreground">{t("simulation.config.otherRolesNoneFree")}</p>
      ) : null}
      {others.length > 0 && (
        <ul aria-labelledby={headingId} className="grid gap-2">
          {others.map((assignment, index) => {
            const name = nameOf(assignment.resourceId);
            // Il ruolo si può cambiare con uno non ancora usato dall'attività.
            const taken = new Set([task.resourceId, ...others.filter((_, i) => i !== index).map((a) => a.resourceId)]);
            return (
              <li key={assignment.resourceId} data-other-role={assignment.resourceId} className="sim-task-other grid gap-2 rounded-md border border-border bg-card p-2.5">
                <div className="flex items-end gap-2">
                  <label className="grid min-w-0 flex-1 gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.role")}</span>
                    <Select value={assignment.resourceId} onValueChange={(value) => update(index, { ...assignment, resourceId: value })}>
                      <SelectTrigger size="sm" className="w-full" aria-label={t("simulation.config.otherRoleOf", { task: taskName })}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {resources.filter((r) => !taken.has(r.id)).map((r) => (
                          <SelectItem key={r.id} value={r.id}>{roleLabel(r)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </label>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    aria-label={t("simulation.config.removeOtherRole", { role: name, task: taskName })}
                    onClick={() => onChange({ ...task, otherAssignments: others.filter((_, i) => i !== index) })}
                  >
                    <X aria-hidden className="size-4" />
                  </Button>
                </div>
                <TaskDurationFields
                  elementId={`${elementId}-${assignment.resourceId}`}
                  taskName={`${taskName} · ${name}`}
                  task={assignment}
                  onChange={(next) => update(index, next)}
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
