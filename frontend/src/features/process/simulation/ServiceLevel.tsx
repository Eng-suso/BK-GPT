import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { formatDuration, formatPercent } from "./simulationResults";
import type { CaseAttributeDraft } from "./caseRules";
import type { SlaDraft } from "./simulationScenario";
import {
  MAX_SLA_SEGMENTS,
  goalIssue,
  newSlaSegment,
  segmentAttributes,
  slaSegmentIssues,
  type SlaGoalDraft,
  type SlaSegmentDraft,
} from "./slaSegments";
import type { SimulationRun } from "./simulationTypes";

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/** SIM-13: l'obiettivo di servizio dello scenario, nel pannello. SIM-13b: e per gruppo di casi. */
export function ServiceLevelFields({ sla, attributes = [], onChange }: {
  sla: SlaDraft | undefined;
  attributes?: CaseAttributeDraft[];
  onChange: (next: SlaDraft | undefined) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const issue = sla ? goalIssue(sla) : null;
  return (
    <fieldset className="mt-1 grid gap-2 rounded-md border border-border p-2.5" data-sim-sla>
      <legend className="px-1 text-xs font-medium text-foreground">{t("simulation.config.sla")}</legend>
      <p className="text-xs text-muted-foreground">{t("simulation.config.slaHint")}</p>
      {sla ? (
        <>
          <GoalFields goal={sla} issue={issue} issueId="sim-sla-issue" label="" onChange={(goal) => onChange({ ...sla, ...goal })} />
          {issue
            ? <p id="sim-sla-issue" role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.slaIssue.${issue}`)}</p>
            : <p className="text-xs text-muted-foreground">{t("simulation.config.slaReads", { share: sla.sharePercent, target: sla.target, unit: unitLabel(t, sla.unit) })}</p>}
          <SegmentGoals sla={sla} attributes={attributes} onChange={onChange} />
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

/** SIM-13b: gli obiettivi propri di un gruppo di casi, sotto quello di tutti. */
function SegmentGoals({ sla, attributes, onChange }: {
  sla: SlaDraft;
  attributes: CaseAttributeDraft[];
  onChange: (next: SlaDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const segments = sla.segments ?? [];
  const usable = segmentAttributes(attributes);
  const issues = slaSegmentIssues(segments, attributes);
  const next = newSlaSegment(attributes, segments, sla);
  const set = (list: SlaSegmentDraft[]) => onChange({ ...sla, segments: list.length ? list : undefined });
  const update = (index: number, fields: Partial<SlaSegmentDraft>) =>
    set(segments.map((segment, i) => (i === index ? { ...segment, ...fields } : segment)));

  if (usable.length === 0 && segments.length === 0) {
    return <p className="text-xs text-muted-foreground">{t("simulation.config.slaSegments.needAttribute")}</p>;
  }
  return (
    <div className="grid gap-2 border-t border-border pt-2" data-sim-sla-segments>
      <p className="text-xs font-medium text-foreground">{t("simulation.config.slaSegments.title")}</p>
      {segments.length > 0 && (
        <ul className="grid gap-2">
          {segments.map((segment, index) => {
            const attribute = usable.find((a) => a.id === segment.attributeId);
            const group = attribute ? `${attribute.name.trim()} = ${segment.value}` : t("simulation.config.slaSegments.group", { n: index + 1 });
            const issue = issues[index];
            const issueId = `sim-sla-segment-${index}-issue`;
            return (
              <li key={index} className="grid gap-2 rounded-md border border-border bg-card p-2.5" data-sla-segment={index + 1}>
                <div className="flex items-end gap-2">
                  <label className="grid min-w-0 flex-1 gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaSegments.cases")}</span>
                    <select className={NATIVE_SELECT}
                      aria-label={`${t("simulation.config.slaSegments.cases")} · ${t("simulation.config.slaSegments.group", { n: index + 1 })}`}
                      aria-invalid={issue === "attribute" || issue === "duplicate" || undefined}
                      aria-describedby={issue ? issueId : undefined}
                      value={issue === "attribute" ? "" : `${segment.attributeId}\u0000${segment.value}`}
                      onChange={(e) => {
                        const [attributeId, value] = e.target.value.split("\u0000");
                        update(index, { attributeId, value });
                      }}>
                      {issue === "attribute" && <option value="">{t("simulation.config.slaSegments.choose")}</option>}
                      {usable.map((a) => a.categories.filter((c) => c.value.trim()).map((c) => (
                        <option key={`${a.id}-${c.value}`} value={`${a.id}\u0000${c.value.trim()}`}>{`${a.name.trim()} = ${c.value.trim()}`}</option>
                      )))}
                    </select>
                  </label>
                  <Button type="button" size="icon" variant="ghost"
                    aria-label={t("simulation.config.slaSegments.remove", { group })}
                    onClick={() => set(segments.filter((_, i) => i !== index))}>
                    <X aria-hidden className="size-4" />
                  </Button>
                </div>
                <GoalFields goal={segment} issue={issue === "target" || issue === "share" ? issue : null} issueId={issueId}
                  label={` · ${group}`} onChange={(goal) => update(index, goal)} />
                {issue
                  ? <p id={issueId} role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.slaSegments.issue.${issue}`)}</p>
                  : <p className="text-xs text-muted-foreground">{t("simulation.config.slaSegments.reads", { group, share: segment.sharePercent, target: segment.target, unit: unitLabel(t, segment.unit) })}</p>}
              </li>
            );
          })}
        </ul>
      )}
      <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
        disabled={!next || segments.length >= MAX_SLA_SEGMENTS}
        onClick={() => next && set([...segments, next])}>
        <Plus aria-hidden className="size-3.5" />{t("simulation.config.slaSegments.add")}
      </Button>
    </div>
  );
}

function GoalFields({ goal, issue, issueId, label, onChange }: {
  goal: SlaGoalDraft;
  issue: "target" | "share" | null;
  issueId: string;
  /** Aggiunto ai nomi accessibili: distingue i campi di un gruppo da quelli di tutti i casi. */
  label: string;
  onChange: (goal: SlaGoalDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const goalOnly = { target: goal.target, unit: goal.unit, sharePercent: goal.sharePercent };
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaTarget")}</span>
          <Input className="h-8" type="number" min={0} step="any" value={goal.target}
            aria-label={label ? `${t("simulation.config.slaTarget")}${label}` : undefined}
            aria-invalid={issue === "target" || undefined} aria-describedby={issue ? issueId : undefined}
            onChange={(e) => onChange({ ...goalOnly, target: e.target.value === "" ? 0 : Number(e.target.value) })} />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaUnit")}</span>
          <select className={NATIVE_SELECT} value={goal.unit}
            aria-label={label ? `${t("simulation.config.slaUnit")}${label}` : undefined}
            onChange={(e) => onChange({ ...goalOnly, unit: e.target.value as SlaGoalDraft["unit"] })}>
            <option value="hours">{t("simulation.config.slaHours")}</option>
            <option value="days">{t("simulation.config.slaDays")}</option>
          </select>
        </label>
      </div>
      <label className="grid gap-1">
        <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.slaShare")}</span>
        <Input className="h-8" type="number" min={1} max={100} value={goal.sharePercent}
          aria-label={label ? `${t("simulation.config.slaShare")}${label}` : undefined}
          aria-invalid={issue === "share" || undefined} aria-describedby={issue ? issueId : undefined}
          onChange={(e) => onChange({ ...goalOnly, sharePercent: e.target.value === "" ? 0 : Number(e.target.value) })} />
      </label>
    </>
  );
}

function unitLabel(t: (key: string) => string, unit: SlaGoalDraft["unit"]): string {
  return t(unit === "days" ? "simulation.config.slaDays" : "simulation.config.slaHours").toLowerCase();
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
      {sla.segments && sla.segments.length > 0 && (
        <ul className="mt-1 grid gap-1.5 border-t border-border pt-2" aria-label={t("simulation.config.slaSegments.title")}>
          {sla.segments.map((segment) => {
            const group = `${segment.attribute} = ${segment.value}`;
            return (
              <li key={group} className="grid gap-0.5" data-sla-segment-outcome={group}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-medium text-foreground">{group}</p>
                  {segment.cases > 0
                    ? <StatusIndicator tone={segment.met ? "ok" : "danger"} label={t(segment.met ? "simulation.results.slaMet" : "simulation.results.slaMissed")} />
                    : <StatusIndicator tone="neutral" label={t("simulation.results.slaSegmentEmpty")} />}
                </div>
                {segment.cases > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {t("simulation.results.slaSegmentWithin", {
                      share: shareBelow(segment.share_within, lang),
                      target: formatDuration(segment.target_seconds, lang),
                      goal: formatPercent(segment.share_target),
                      count: segment.late_cases,
                      cases: segment.cases,
                    })}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** Per difetto, a un decimale: un 99,6% non deve leggersi "100%" accanto a "Non rispettato". */
function shareBelow(ratio: number, lang: "it" | "en"): string {
  return `${(Math.floor(ratio * 1000) / 10).toLocaleString(lang === "it" ? "it-IT" : "en-US")}%`;
}
