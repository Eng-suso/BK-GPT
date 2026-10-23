import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { Input } from "@/ui/input";

import { MAX_PERCENT, arrivalMonthIssues, monthsNeedPoisson, newArrivalMonth, type ArrivalMonthDraft } from "./arrivalMonths";
import type { DistributionName } from "./simulationTypes";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";
const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

/**
 * SIM-08b: un ritmo degli arrivi diverso per mese, in percentuale sul ritmo
 * di base (o di ogni fascia). I mesi assenti restano come sono.
 */
export function ArrivalMonths({ months, hasBands, distribution, onChange }: {
  months: ArrivalMonthDraft[] | undefined;
  /** Con le fasce il fattore vale su ognuna; senza, gli arrivi devono essere esponenziali. */
  hasBands: boolean;
  distribution: DistributionName;
  onChange: (months: ArrivalMonthDraft[] | undefined) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const list = months ?? [];
  const issues = arrivalMonthIssues(list);
  const needsPoisson = monthsNeedPoisson(months, hasBands, distribution);
  const monthName = React.useMemo(() => {
    const format = new Intl.DateTimeFormat(i18n.language === "en" ? "en-US" : "it-IT", { month: "long", timeZone: "UTC" });
    return (month: number) => format.format(new Date(Date.UTC(2026, month - 1, 1)));
  }, [i18n.language]);
  const update = (index: number, fields: Partial<ArrivalMonthDraft>) =>
    onChange(list.map((m, i) => (i === index ? { ...m, ...fields } : m)));

  return (
    <div className="grid gap-2" data-arrival-months>
      <label className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Checkbox
          checked={months !== undefined}
          onCheckedChange={(checked) => onChange(checked === true ? [newArrivalMonth([])] : undefined)}
        />
        {t("simulation.config.arrivalMonths.toggle")}
      </label>
      {months !== undefined && (
        <>
          <p className="text-xs text-muted-foreground">
            {t(hasBands ? "simulation.config.arrivalMonths.hintBands" : "simulation.config.arrivalMonths.hint")}
          </p>
          <ul className="grid gap-2">
            {list.map((entry, index) => {
              const name = MONTHS.includes(entry.month) ? monthName(entry.month) : String(index + 1);
              const issue = issues[index];
              const issueId = `sim-arrival-month-${index}-issue`;
              return (
                <li key={index} className="grid grid-cols-[minmax(0,1fr)_96px_auto] items-end gap-2" data-arrival-month={index + 1}>
                  <label className="grid min-w-0 gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.arrivalMonths.month")}</span>
                    <select
                      className={NATIVE_SELECT}
                      aria-label={t("simulation.config.arrivalMonths.monthOf", { n: index + 1 })}
                      aria-invalid={issue === "month" || issue === "duplicate" || undefined}
                      aria-describedby={issue ? issueId : undefined}
                      value={entry.month}
                      onChange={(e) => update(index, { month: Number(e.target.value) })}
                    >
                      {MONTHS.map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
                    </select>
                  </label>
                  <label className="grid gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.arrivalMonths.change")}</span>
                    <span className="relative">
                      <Input
                        className="h-8 pr-6"
                        type="number"
                        min={-99}
                        max={MAX_PERCENT}
                        step="any"
                        aria-label={t("simulation.config.arrivalMonths.changeOf", { month: name })}
                        aria-invalid={issue === "percent" || undefined}
                        aria-describedby={issue ? issueId : undefined}
                        value={Number.isFinite(entry.percent) ? entry.percent : ""}
                        onChange={(e) => update(index, { percent: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
                      />
                      <span aria-hidden className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-micro text-muted-foreground">%</span>
                    </span>
                  </label>
                  <Button type="button" size="icon" variant="ghost"
                    aria-label={t("simulation.config.arrivalMonths.remove", { month: name })}
                    onClick={() => onChange(list.length > 1 ? list.filter((_, i) => i !== index) : undefined)}>
                    <X aria-hidden className="size-4" />
                  </Button>
                  {issue && (
                    <p id={issueId} role="alert" className="col-span-3 text-xs font-medium text-destructive">
                      {t(`simulation.config.arrivalMonths.issue.${issue}`)}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
          {list.length < 12 && (
            <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
              onClick={() => onChange([...list, newArrivalMonth(list)])}>
              <Plus aria-hidden className="size-3.5" />
              {t("simulation.config.arrivalMonths.add")}
            </Button>
          )}
          {needsPoisson && (
            <p role="alert" className="text-xs font-medium text-destructive">{t("simulation.config.arrivalMonths.issue.needsPoisson")}</p>
          )}
        </>
      )}
    </div>
  );
}
