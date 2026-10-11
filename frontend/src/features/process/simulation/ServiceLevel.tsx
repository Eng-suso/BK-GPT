import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { formatDuration, formatPercent } from "./simulationResults";
import { slaIssue, type SlaDraft } from "./simulationScenario";
import type { SimulationRun } from "./simulationTypes";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/** SIM-13: l'obiettivo di servizio dello scenario, nel pannello. */
export function ServiceLevelFields({ sla, onChange }: { sla: SlaDraft | undefined; onChange: (next: SlaDraft | undefined) => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  const issue = sla ? slaIssue(sla) : null;
  return (
    <fieldset className="mt-1 grid gap-2 rounded-md border border-border p-2.5" data-sim-sla>
      <legend className="px-1 text-xs font-medium text-foreground">{t("simulation.config.sla")}</legend>
      <p className="text-xs text-muted-foreground">{t("simulation.config.slaHint")}</p>
      {sla ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1">
              <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaTarget")}</span>
              <Input className="h-8" type="number" min={0} step="any" value={sla.target}
                aria-invalid={issue === "target" || undefined} aria-describedby={issue ? "sim-sla-issue" : undefined}
                onChange={(e) => onChange({ ...sla, target: e.target.value === "" ? 0 : Number(e.target.value) })} />
            </label>
            <label className="grid gap-1">
              <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaUnit")}</span>
              <select className={NATIVE_SELECT} value={sla.unit} onChange={(e) => onChange({ ...sla, unit: e.target.value as SlaDraft["unit"] })}>
                <option value="hours">{t("simulation.config.slaHours")}</option>
                <option value="days">{t("simulation.config.slaDays")}</option>
              </select>
            </label>
          </div>
          <label className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaShare")}</span>
            <Input className="h-8" type="number" min={1} max={100} value={sla.sharePercent}
              aria-invalid={issue === "share" || undefined} aria-describedby={issue ? "sim-sla-issue" : undefined}
              onChange={(e) => onChange({ ...sla, sharePercent: e.target.value === "" ? 0 : Number(e.target.value) })} />
          </label>
          {issue
            ? <p id="sim-sla-issue" role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.slaIssue.${issue}`)}</p>
            : <p className="text-xs text-muted-foreground">{t("simulation.config.slaReads", { share: sla.sharePercent, target: sla.target, unit: t(sla.unit === "days" ? "simulation.config.slaDays" : "simulation.config.slaHours").toLowerCase() })}</p>}
          <Button type="button" size="sm" variant="ghost" className="h-7 w-fit gap-1 px-2 text-xs" onClick={() => onChange(undefined)}>
            <X aria-hidden className="size-3.5" />{t("simulation.config.slaRemove")}
          </Button>
        </>
      ) : (
        <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
          onClick={() => onChange({ target: 2, unit: "days", sharePercent: 90 })}>
          <Plus aria-hidden className="size-3.5" />{t("simulation.config.slaAdd")}
        </Button>
      )}
    </fieldset>
  );
}

/** SIM-13: l'esito dell'obiettivo sul run, sopra i risultati. Niente se lo scenario non ne aveva. */
export function ServiceLevelOutcome({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const sla = run.summary?.sla;
  if (!sla) return null;
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  return (
    <section aria-label={t("simulation.config.sla")} className="mb-3 grid gap-1 rounded-md border border-border p-3" data-sim-sla-outcome>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">{t("simulation.config.sla")}</p>
        <StatusIndicator tone={sla.met ? "ok" : "danger"} label={t(sla.met ? "simulation.results.slaMet" : "simulation.results.slaMissed")} />
      </div>
      <p className="text-sm text-foreground">
        {t("simulation.results.slaWithin", { share: shareBelow(sla.share_within, lang), target: formatDuration(sla.target_seconds, lang), goal: formatPercent(sla.share_target) })}
      </p>
      <p className="text-xs text-muted-foreground">{t("simulation.results.slaLate", { count: sla.late_cases, cases: sla.cases })}</p>
    </section>
  );
}

/** Per difetto, a un decimale: un 99,6% non deve leggersi "100%" accanto a "Non rispettato". */
function shareBelow(ratio: number, lang: "it" | "en"): string {
  return `${(Math.floor(ratio * 1000) / 10).toLocaleString(lang === "it" ? "it-IT" : "en-US")}%`;
}
