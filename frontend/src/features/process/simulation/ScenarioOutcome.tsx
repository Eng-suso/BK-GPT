import React from "react";
import { useTranslation } from "react-i18next";
import { CalendarCheck, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/ui/select";
import { cn } from "@/lib/utils";

import { useEventLogs } from "./eventlog/useEventLogImport";
import {
  predictedSnapshot,
  scenarioDisplayName,
  type ScenarioOutcome,
  type ScenarioOutcomeInput,
  type ScenarioRuns,
  type WorkspaceScenario,
  type scenarioDeltas,
} from "./scenarioWorkspace";

type Lang = "it" | "en";
type Kpi = ScenarioOutcome["kpis"][number];

/**
 * SIM-28: previsto contro osservato. Un'alternativa implementata riceve la
 * data; con un log reale che copre il prima e il dopo DeliR dice quanto aveva
 * ragione la previsione, KPI per KPI, sulle variazioni relative.
 */
export function ScenarioOutcomes({ processId, alternatives, asIs, onRecord, lang }: {
  processId: string;
  alternatives: { scenario: WorkspaceScenario; results: ScenarioRuns; comparison: ReturnType<typeof scenarioDeltas> | null }[];
  asIs: ScenarioRuns | null;
  onRecord: (scenario: WorkspaceScenario, body: ScenarioOutcomeInput | null) => Promise<boolean>;
  lang: Lang;
}): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const shown = alternatives.filter(({ scenario, results }) => scenario.outcome || (asIs?.completed.length && results.completed.length));
  if (!shown.length) return null;
  return (
    <section className="grid gap-2" aria-labelledby="sim-outcomes-title" data-sim-outcomes>
      <div className="grid gap-0.5">
        <h4 id="sim-outcomes-title" className="text-xs font-semibold text-foreground">{t("simulation.outcome.title")}</h4>
        <p className="text-xs text-muted-foreground">{t("simulation.outcome.intro")}</p>
      </div>
      <ul className="grid gap-2">
        {shown.map(({ scenario, results, comparison }) => (
          <li key={scenario.id} className="ui-surface ui-surface-inset grid gap-2 p-2.5" data-sim-outcome={scenario.label}>
            {scenario.outcome
              ? <OutcomeView scenario={scenario} outcome={scenario.outcome} lang={lang} onClear={() => void onRecord(scenario, null)} />
              : asIs && comparison
                ? <OutcomeForm processId={processId} scenario={scenario} onSubmit={(dates) => onRecord(scenario, {
                    ...dates,
                    as_is_run_id: asIs.latest?.id ?? null,
                    alternative_run_id: results.latest?.id ?? null,
                    predicted: predictedSnapshot(asIs, results, comparison),
                  })} />
                : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function OutcomeForm({ processId, scenario, onSubmit }: {
  processId: string;
  scenario: WorkspaceScenario;
  onSubmit: (input: Pick<ScenarioOutcomeInput, "implemented_on" | "before_event_log_id" | "after_event_log_id">) => Promise<boolean>;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const name = scenarioDisplayName(scenario);
  const [open, setOpen] = React.useState(false);
  const [day, setDay] = React.useState("");
  const [before, setBefore] = React.useState("");
  const [after, setAfter] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const logs = useEventLogs(processId);
  const mapped = (logs.data ?? []).filter((log) => log.status === "mapped");

  if (!open) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-foreground">{name}</p>
        <Button size="sm" variant="outline" aria-label={t("simulation.outcome.recordFor", { name })} onClick={() => setOpen(true)}>
          <CalendarCheck aria-hidden className="size-3.5" />
          {t("simulation.outcome.record")}
        </Button>
      </div>
    );
  }
  const beforeId = before || mapped[0]?.id || "";
  const afterId = after || beforeId;
  const ready = Boolean(day && beforeId && afterId) && !busy;
  return (
    <form className="grid gap-2" aria-label={t("simulation.outcome.formFor", { name })} onSubmit={(event) => {
      event.preventDefault();
      if (!ready) return;
      setBusy(true);
      void onSubmit({ implemented_on: day, before_event_log_id: beforeId, after_event_log_id: afterId })
        .then((saved) => { if (saved) setOpen(false); })
        .finally(() => setBusy(false));
    }}>
      <p className="text-xs font-medium text-foreground">{name}</p>
      {!logs.isLoading && mapped.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-sim-outcome-nolog>{t("simulation.outcome.noLog")}</p>
      ) : (
        <>
          <label className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">{t("simulation.outcome.implementedOn")}</span>
            <Input className="h-8 w-44" type="date" required value={day} onChange={(e) => setDay(e.target.value)}
              aria-label={`${t("simulation.outcome.implementedOn")} · ${name}`} />
          </label>
          <div className="grid gap-2 sm:grid-cols-2">
            {([["before", beforeId, setBefore], ["after", afterId, setAfter]] as const).map(([side, value, set]) => (
              <div key={side} className="grid gap-1">
                <span className="text-xs font-medium text-muted-foreground">{t(`simulation.outcome.${side}Log`)}</span>
                <Select value={value} onValueChange={set}>
                  <SelectTrigger size="sm" className="w-full" aria-label={`${t(`simulation.outcome.${side}Log`)} · ${name}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {mapped.map((log) => <SelectItem key={log.id} value={log.id}>{log.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{t("simulation.outcome.periodHint")}</p>
        </>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" type="submit" disabled={!ready}>{t("simulation.outcome.measure")}</Button>
        <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>{t("simulation.outcome.cancel")}</Button>
      </div>
    </form>
  );
}

function OutcomeView({ scenario, outcome, lang, onClear }: {
  scenario: WorkspaceScenario;
  outcome: ScenarioOutcome;
  lang: Lang;
  onClear: () => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const name = scenarioDisplayName(scenario);
  const locale = lang === "it" ? "it-IT" : "en-US";
  const percent = new Intl.NumberFormat(locale, { style: "percent", signDisplay: "exceptZero", maximumFractionDigits: 1 });
  const points = (value: number) => t("simulation.outcome.points", { value: new Intl.NumberFormat(locale, { signDisplay: "exceptZero", maximumFractionDigits: 1 }).format(value * 100) });
  const day = new Date(`${outcome.implemented_on}T00:00:00`).toLocaleDateString(locale);
  const predicted = (kpi: Kpi) => kpi.predicted_low != null && kpi.predicted_high != null
    ? t("simulation.outcome.predictedRange", { value: percent.format(kpi.predicted_change), low: percent.format(kpi.predicted_low), high: percent.format(kpi.predicted_high) })
    : percent.format(kpi.predicted_change);
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-foreground">{t("simulation.outcome.implemented", { name, day })}</p>
          <p className="text-xs text-muted-foreground">{t("simulation.outcome.logs", {
            before: outcome.before.name, beforeCases: outcome.before.cases, after: outcome.after.name, afterCases: outcome.after.cases,
          })}</p>
        </div>
        <Button size="sm" variant="ghost" aria-label={t("simulation.outcome.clearFor", { name })} onClick={onClear}>
          <X aria-hidden className="size-3.5" />
          {t("simulation.outcome.clear")}
        </Button>
      </div>
      <ul className="grid gap-1.5" aria-label={t("simulation.outcome.tableFor", { name })}>
        {outcome.kpis.map((kpi) => (
          <li key={kpi.kpi} className="grid gap-1 rounded-md border border-border bg-card p-2" data-sim-outcome-kpi={kpi.kpi}>
            <p className="text-xs font-medium text-foreground">{t(`simulation.results.replicationKpi.${kpi.kpi}`)}</p>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
              <dt className="text-muted-foreground">{t("simulation.outcome.predicted")}</dt>
              <dd className="tabular-nums text-foreground">{predicted(kpi)}</dd>
              <dt className="text-muted-foreground">{t("simulation.outcome.observed")}</dt>
              <dd className="tabular-nums text-foreground">{kpi.observed_change != null ? percent.format(kpi.observed_change) : t("simulation.outcome.notMeasured")}</dd>
              {kpi.error != null && <>
                <dt className="text-muted-foreground">{t("simulation.outcome.error")}</dt>
                <dd className="tabular-nums text-foreground">{points(kpi.error)}</dd>
              </>}
            </dl>
            {kpi.observed_change != null && (
              <p className={cn("text-xs",
                kpi.within === true && "text-[var(--state-success-text)]",
                kpi.within === false && "text-[var(--state-warning-text)]",
                kpi.within == null && "text-muted-foreground")} data-sim-outcome-verdict>
                {t(kpi.within === true ? "simulation.outcome.within" : kpi.within === false ? "simulation.outcome.outside" : "simulation.outcome.noInterval")}
              </p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
