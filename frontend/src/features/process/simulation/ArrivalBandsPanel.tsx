import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { Input } from "@/ui/input";

import { BAND_ATTRIBUTE_NAME, MAX_BANDS, arrivalBandIssues, newArrivalBand, type ArrivalBandDraft } from "./arrivalBands";
import { WEEKDAYS, type Weekday } from "./simulationTypes";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/**
 * SIM-08: un ritmo degli arrivi per fascia oraria. Con le fasce, distribuzione e
 * calendario degli arrivi non contano: fuori dalle fasce non arriva nessuno.
 */
export function ArrivalBands({ bands, onChange, asAttribute = false, onAsAttributeChange }: {
  bands: ArrivalBandDraft[] | undefined;
  onChange: (bands: ArrivalBandDraft[] | undefined) => void;
  /** SIM-33: la fascia di arrivo diventa l'attributo del caso `fascia_arrivo`. */
  asAttribute?: boolean;
  onAsAttributeChange?: (enabled: boolean) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const list = bands ?? [];
  const issues = arrivalBandIssues(list);
  const update = (index: number, fields: Partial<ArrivalBandDraft>) =>
    onChange(list.map((band, i) => (i === index ? { ...band, ...fields } : band)));

  return (
    <div className="grid gap-2" data-arrival-bands>
      <label className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Checkbox
          checked={bands !== undefined}
          onCheckedChange={(checked) => onChange(checked === true ? [newArrivalBand([])] : undefined)}
        />
        {t("simulation.config.arrivalBands.toggle")}
      </label>
      {bands !== undefined && (
        <>
          <p className="text-xs text-muted-foreground">{t("simulation.config.arrivalBands.hint")}</p>
          <ul className="grid gap-2">
            {list.map((band, index) => {
              const label = t("simulation.config.arrivalBands.band", { n: index + 1 });
              const issue = issues[index];
              const issueId = `sim-arrival-band-${index}-issue`;
              return (
                <li key={index} className="grid gap-2 rounded-md border border-border bg-card p-2.5" data-arrival-band={index + 1}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">{label}</p>
                    <Button type="button" size="icon" variant="ghost"
                      aria-label={t("simulation.config.arrivalBands.remove", { band: label })}
                      onClick={() => onChange(list.length > 1 ? list.filter((_, i) => i !== index) : undefined)}>
                      <X aria-hidden className="size-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Day label={`${t("simulation.config.fromDay")} · ${label}`} text={t("simulation.config.fromDay")}
                      value={band.fromDay} onChange={(fromDay) => update(index, { fromDay })} />
                    <Day label={`${t("simulation.config.toDay")} · ${label}`} text={t("simulation.config.toDay")}
                      value={band.toDay} onChange={(toDay) => update(index, { toDay })} />
                    <Clock label={`${t("simulation.config.begin")} · ${label}`} text={t("simulation.config.begin")}
                      value={band.begin} invalid={issue === "order" || issue === "overlap"} describedBy={issue ? issueId : undefined}
                      onChange={(begin) => update(index, { begin })} />
                    <Clock label={`${t("simulation.config.end")} · ${label}`} text={t("simulation.config.end")}
                      value={band.end} invalid={issue === "order" || issue === "overlap"} describedBy={issue ? issueId : undefined}
                      onChange={(end) => update(index, { end })} />
                  </div>
                  <label className="grid gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.arrivalBands.mean")}</span>
                    <Input
                      className="h-8"
                      type="number"
                      min={0}
                      step="any"
                      aria-label={`${t("simulation.config.arrivalBands.mean")} · ${label}`}
                      aria-invalid={issue === "mean" || undefined}
                      aria-describedby={issue ? issueId : undefined}
                      value={Number.isFinite(band.meanMinutes) ? band.meanMinutes : ""}
                      onChange={(e) => update(index, { meanMinutes: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
                    />
                  </label>
                  {issue && <p id={issueId} role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.arrivalBands.issue.${issue}`)}</p>}
                </li>
              );
            })}
          </ul>
          <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
            disabled={list.length >= MAX_BANDS}
            onClick={() => onChange([...list, newArrivalBand(list)])}>
            <Plus aria-hidden className="size-3.5" />
            {t("simulation.config.arrivalBands.add")}
          </Button>
          {onAsAttributeChange && (
            <div className="grid gap-1" data-arrival-band-attribute>
              <label className="flex items-center gap-2 text-xs font-medium text-foreground">
                <Checkbox checked={asAttribute} onCheckedChange={(checked) => onAsAttributeChange(checked === true)}
                  aria-describedby="sim-arrival-band-attribute-hint" />
                {t("simulation.config.arrivalBands.asAttribute")}
              </label>
              <p id="sim-arrival-band-attribute-hint" className="text-xs text-muted-foreground">
                {t("simulation.config.arrivalBands.asAttributeHint", { name: BAND_ATTRIBUTE_NAME })}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function Day({ label, text, value, onChange }: { label: string; text: string; value: Weekday; onChange: (day: Weekday) => void }) {
  const { t } = useTranslation("process");
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{text}</span>
      <select className={NATIVE_SELECT} aria-label={label} value={value} onChange={(e) => onChange(e.target.value as Weekday)}>
        {WEEKDAYS.map((day) => <option key={day} value={day}>{t(`simulation.config.weekday.${day}`)}</option>)}
      </select>
    </label>
  );
}

export function Clock({ label, text, value, invalid, describedBy, onChange }: {
  label: string;
  text: string;
  value: string;
  invalid: boolean;
  describedBy?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{text}</span>
      <Input className="h-8" type="time" aria-label={label} value={value.slice(0, 5)}
        aria-invalid={invalid || undefined} aria-describedby={describedBy} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
