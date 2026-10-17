import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { shiftIssue, type CalendarDraft, type ResourceDraft, type ShiftDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * SIM-30: turni di rinforzo di un ruolo ("due in più dalle 9 alle 12"). Ogni
 * turno sono unità in più presenti solo negli orari del suo calendario.
 */
export function ResourceShifts({ resource, calendars, onChange }: {
  resource: ResourceDraft;
  calendars: CalendarDraft[];
  onChange: (shifts: ShiftDraft[] | undefined) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const shifts = resource.shifts ?? [];
  const update = (index: number, next: Partial<ShiftDraft>) => onChange(shifts.map((s, i) => (i === index ? { ...s, ...next } : s)));

  return (
    <div className="mt-3 grid gap-2 border-t border-border pt-3" data-resource-shifts={resource.id}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-foreground">{t("simulation.config.shifts.title")}</p>
        <Button type="button" size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs"
          aria-label={t("simulation.config.shifts.addFor", { role: resource.name })}
          disabled={calendars.length === 0 || shifts.length >= 10}
          onClick={() => onChange([...shifts, { amount: 1, calendarId: calendars[0].id }])}>
          <Plus aria-hidden className="size-3.5" />
          {t("simulation.config.shifts.add")}
        </Button>
      </div>
      {calendars.length === 0
        ? <p className="text-xs text-muted-foreground">{t("simulation.config.shifts.noCalendars")}</p>
        : shifts.length === 0 && <p className="text-xs text-muted-foreground">{t("simulation.config.shifts.hint")}</p>}
      {shifts.length > 0 && (
        <ul className="grid gap-2">
          {shifts.map((shift, index) => {
            const label = t("simulation.config.shifts.label", { role: resource.name, n: index + 2 });
            const issue = shiftIssue(shift, calendars);
            const issueId = `sim-shift-${resource.id}-${index}-issue`;
            return (
              <li key={index} className="grid grid-cols-[5rem_minmax(0,1fr)_auto] items-end gap-2" data-shift={index + 2}>
                <label className="grid gap-1">
                  <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.shifts.amount")}</span>
                  <Input className="h-8" type="number" min={1} max={1000} step={1}
                    aria-label={`${t("simulation.config.shifts.amount")} · ${label}`}
                    aria-invalid={issue === "amount" || undefined} aria-describedby={issue ? issueId : undefined}
                    value={Number.isFinite(shift.amount) ? shift.amount : ""}
                    onChange={(e) => update(index, { amount: e.target.value === "" ? Number.NaN : Number(e.target.value) })} />
                </label>
                <label className="grid min-w-0 gap-1">
                  <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.shifts.calendar")}</span>
                  <select className={NATIVE_SELECT} aria-label={`${t("simulation.config.shifts.calendar")} · ${label}`}
                    aria-invalid={issue === "calendar" || undefined} aria-describedby={issue ? issueId : undefined}
                    value={calendars.some((c) => c.id === shift.calendarId) ? shift.calendarId : ""}
                    onChange={(e) => update(index, { calendarId: e.target.value })}>
                    {issue === "calendar" && <option value="">{t("simulation.config.shifts.chooseCalendar")}</option>}
                    {calendars.map((c) => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
                  </select>
                </label>
                <Button type="button" size="icon" variant="ghost" aria-label={t("simulation.config.shifts.remove", { shift: label })}
                  onClick={() => onChange(shifts.length > 1 ? shifts.filter((_, i) => i !== index) : undefined)}>
                  <X aria-hidden className="size-4" />
                </Button>
                {issue && <p id={issueId} role="alert" className="col-span-3 text-xs font-medium text-destructive">{t(`simulation.config.shifts.issue.${issue}`)}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
