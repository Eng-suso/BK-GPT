import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { WEEKDAYS, type SimCalendar, type Weekday } from "./simulationTypes";
import { calendarIssue, newCalendarId, type CalendarDraft } from "./simulationScenario";

type Period = CalendarDraft["periods"][number];

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

const DEFAULT_PERIOD: Period = { from_day: "MONDAY", to_day: "FRIDAY", begin: "09:00", end: "17:00" };

/** «Lun–Ven 09:00–17:00; Sab 09:00–13:00» */
function useCalendarSummary(): (calendar: SimCalendar) => string {
  const { t } = useTranslation("process");
  return (calendar) => calendar.periods.map((p) => {
    const days = p.from_day === p.to_day
      ? t(`simulation.config.weekdayShort.${p.from_day}`)
      : `${t(`simulation.config.weekdayShort.${p.from_day}`)}–${t(`simulation.config.weekdayShort.${p.to_day}`)}`;
    return `${days} ${p.begin.slice(0, 5)}–${p.end.slice(0, 5)}`;
  }).join("; ");
}

/**
 * I calendari di lavoro dello scenario. Quello standard viene dal backend e non si modifica:
 * vale per gli arrivi e per le risorse senza calendario proprio.
 */
export function CalendarsSection({
  standard,
  calendars,
  onChange,
}: {
  standard: SimCalendar | null | undefined;
  calendars: CalendarDraft[];
  onChange: (next: CalendarDraft[]) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const summary = useCalendarSummary();
  const update = (id: string, next: Partial<CalendarDraft>) =>
    onChange(calendars.map((c) => (c.id === id ? { ...c, ...next } : c)));
  const updatePeriod = (calendar: CalendarDraft, index: number, next: Partial<Period>) =>
    update(calendar.id, { periods: calendar.periods.map((p, i) => (i === index ? { ...p, ...next } : p)) });

  return (
    <div className="grid gap-3">
      <p className="text-sm leading-relaxed text-muted-foreground">{t("simulation.config.calendarsHint")}</p>
      {standard && (
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <p className="text-xs font-medium text-muted-foreground">{t("simulation.config.standardCalendar")}</p>
          <p className="mt-1 text-sm text-foreground">{summary(standard)}</p>
        </div>
      )}
      <ul className="grid gap-3">
        {calendars.map((calendar) => {
          const issue = calendarIssue(calendar);
          const issueId = `sim-calendar-issue-${calendar.id}`;
          return (
            <li key={calendar.id} data-calendar-id={calendar.id} className="min-w-0 rounded-lg border border-border bg-card p-3">
              <div className="mb-3 flex items-end gap-2">
                <label className="grid min-w-0 flex-1 gap-1">
                  <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.calendarName")}</span>
                  <Input
                    className="h-8"
                    value={calendar.name}
                    aria-invalid={issue === "name" ? true : undefined}
                    aria-describedby={issue ? issueId : undefined}
                    onChange={(e) => update(calendar.id, { name: e.target.value })}
                  />
                </label>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`${t("simulation.config.removeCalendar")} ${calendar.name}`}
                  onClick={() => onChange(calendars.filter((c) => c.id !== calendar.id))}
                >
                  <X aria-hidden className="size-4" />
                </Button>
              </div>
              <ul className="grid gap-2">
                {calendar.periods.map((period, index) => (
                  <li key={index} className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_0.8fr_0.8fr_auto] sm:items-end">
                    <DaySelect label={t("simulation.config.fromDay")} value={period.from_day} onChange={(from_day) => updatePeriod(calendar, index, { from_day })} />
                    <DaySelect label={t("simulation.config.toDay")} value={period.to_day} onChange={(to_day) => updatePeriod(calendar, index, { to_day })} />
                    <TimeField label={t("simulation.config.begin")} value={period.begin} invalid={issue === "periodOrder"} describedBy={issue ? issueId : undefined} onChange={(begin) => updatePeriod(calendar, index, { begin })} />
                    <TimeField label={t("simulation.config.end")} value={period.end} invalid={issue === "periodOrder"} describedBy={issue ? issueId : undefined} onChange={(end) => updatePeriod(calendar, index, { end })} />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`${t("simulation.config.removePeriod")} ${index + 1}`}
                      onClick={() => update(calendar.id, { periods: calendar.periods.filter((_, i) => i !== index) })}
                    >
                      <X aria-hidden className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="mt-2 h-7 gap-1 px-2 text-xs"
                onClick={() => update(calendar.id, { periods: [...calendar.periods, { ...DEFAULT_PERIOD }] })}
              >
                <Plus aria-hidden className="size-3.5" />
                {t("simulation.config.addPeriod")}
              </Button>
              {issue && (
                <p id={issueId} role="alert" className="mt-2 text-xs font-medium text-destructive">
                  {t(`simulation.config.calendarIssue.${issue}`)}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => onChange([
            ...calendars,
            {
              id: newCalendarId(calendars),
              name: t("simulation.config.newCalendarName", { n: calendars.length + 1 }),
              periods: [{ ...(standard?.periods[0] ?? DEFAULT_PERIOD) }],
            },
          ])}
        >
          <Plus aria-hidden className="size-3.5" />
          {t("simulation.config.addCalendar")}
        </Button>
      </div>
    </div>
  );
}

function DaySelect({ label, value, onChange }: { label: string; value: Weekday; onChange: (day: Weekday) => void }) {
  const { t } = useTranslation("process");
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select className={NATIVE_SELECT} value={value} onChange={(e) => onChange(e.target.value as Weekday)}>
        {WEEKDAYS.map((day) => <option key={day} value={day}>{t(`simulation.config.weekday.${day}`)}</option>)}
      </select>
    </label>
  );
}

function TimeField({ label, value, invalid, describedBy, onChange }: {
  label: string;
  value: string;
  invalid: boolean;
  describedBy?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input
        className="h-8"
        type="time"
        value={value.slice(0, 5)}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
