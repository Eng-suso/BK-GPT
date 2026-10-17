import React from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/ui/input";

import { MAX_HORIZON_DAYS, horizonIssue, type ScenarioDraft } from "./simulationScenario";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";
const DEFAULT_DAYS = 20;

/**
 * Quanto simulare: un numero di casi, o un periodo (SIM-03). Con il periodo i
 * casi li stima il servizio dal ritmo degli arrivi, e a fine periodo quelli non
 * finiti restano aperti.
 */
export function RunLength({ draft, onChange }: {
  draft: ScenarioDraft;
  onChange: (fields: Pick<ScenarioDraft, "totalCases" | "horizonDays">) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const period = draft.horizonDays !== undefined;
  const issue = horizonIssue(draft);
  return (
    <div className="grid gap-1.5 sm:col-span-2" data-sim-run-length>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5">
          <span className="text-xs text-muted-foreground">{t("simulation.config.runLength.by")}</span>
          <select className={NATIVE_SELECT} value={period ? "period" : "cases"}
            onChange={(e) => onChange({ totalCases: draft.totalCases, horizonDays: e.target.value === "period" ? DEFAULT_DAYS : undefined })}>
            <option value="cases">{t("simulation.config.runLength.cases")}</option>
            <option value="period">{t("simulation.config.runLength.period")}</option>
          </select>
        </label>
        {period ? (
          <label className="grid gap-1.5">
            <span className="text-xs text-muted-foreground">{t("simulation.config.runLength.days")}</span>
            <Input className="h-8" type="number" min={1} max={MAX_HORIZON_DAYS} step={1}
              value={Number.isFinite(draft.horizonDays) ? draft.horizonDays : ""}
              aria-invalid={issue ? true : undefined} aria-describedby="sim-run-length-hint"
              onChange={(e) => onChange({ totalCases: draft.totalCases, horizonDays: e.target.value === "" ? Number.NaN : Number(e.target.value) })} />
          </label>
        ) : (
          <label className="grid gap-1.5">
            <span className="text-xs text-muted-foreground">{t("simulation.fields.cases")}</span>
            <Input className="h-8" type="number" min={1} max={100000} value={draft.totalCases}
              onChange={(e) => onChange({ totalCases: e.target.value === "" ? 0 : Number(e.target.value), horizonDays: undefined })} />
          </label>
        )}
      </div>
      {period && (issue
        ? <p id="sim-run-length-hint" role="alert" className="text-xs font-medium text-destructive">{t("simulation.config.runLength.issue", { max: MAX_HORIZON_DAYS })}</p>
        : <p id="sim-run-length-hint" className="text-xs text-muted-foreground">{t("simulation.config.runLength.hint", { count: draft.horizonDays })}</p>)}
    </div>
  );
}
