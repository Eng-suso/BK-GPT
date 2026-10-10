import React from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Dices, Pencil, Play, ScanEye } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { cn } from "@/lib/utils";

import { formatCurrency, formatDuration } from "./simulationResults";
import type { ReplicationKpi } from "./replications";
import {
  WORKSPACE_KPIS,
  scenarioDeltas,
  scenarioDisplayName,
  scenarioRuns,
  scenarioValue,
  workspaceScenarios,
  type ScenarioDelta,
  type ScenarioRuns,
  type WorkspaceScenario,
} from "./scenarioWorkspace";
import { useScenarioLab } from "./useScenarioLab";
import { useSimulationSection } from "./useSimulationSection";

const STATUS_TONE = {
  never: "text-muted-foreground",
  pending: "text-[var(--color-status-info)]",
  failed: "text-[var(--state-invalid-text)]",
  stale: "text-[var(--state-warning-text)]",
  current: "text-[var(--state-success-text)]",
} as const;

/**
 * SIM-14: il workspace degli scenari. Ogni riga e' uno scenario con il suo
 * ultimo run (o gruppo di ripetizioni); ogni alternativa dice la differenza
 * dall'AS-IS con l'intervallo al 95%, e "migliore" solo se l'intervallo esclude
 * lo zero.
 */
export function ScenarioWorkspacePanel(): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const lab = useScenarioLab();
  const { runs } = useSimulationSection();
  const [params, setParams] = useSearchParams();
  const [starting, setStarting] = React.useState<Set<number>>(new Set());
  const { workspace } = lab;

  const rows = React.useMemo(() => {
    if (!workspace) return [];
    return workspaceScenarios(workspace).map((scenario) => ({ scenario, results: scenarioRuns(workspace, scenario, runs) }));
  }, [workspace, runs]);
  const asIs = rows[0]?.results ?? null;
  const openScenario = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("scenario"); else next.set("scenario", String(id));
    next.set("panel", "scenario");
    setParams(next);
  };

  if (!workspace) {
    if (lab.workspaceError) return <p role="alert" className="sim-scenario-error">{lab.workspaceError}</p>;
    return <div className="grid gap-2" aria-label={t("simulation.scenarios.workspace.loading")}><Skeleton className="h-6 w-2/3" /><Skeleton className="h-40 w-full" /></div>;
  }
  if (!workspace.baseline) {
    return <EmptyState variant="inline" title={t("simulation.scenarios.workspace.empty")} action={<Button size="sm" onClick={() => openScenario(null)}>{t("simulation.scenarios.workspace.openScenario")}</Button>} />;
  }

  const showOnProcess = (scenarioResults: ScenarioRuns) => {
    const reference = asIs?.completed[0];
    const alternative = scenarioResults.completed[0];
    if (!reference || !alternative) return;
    const next = new URLSearchParams(params);
    next.set("a", String(reference.id));
    next.set("b", String(alternative.id));
    next.set("compareMode", "delta");
    next.set("view", "compare");
    next.set("panel", "compare");
    setParams(next);
  };
  const run = async (scenarios: WorkspaceScenario[]) => {
    setStarting((current) => new Set([...current, ...scenarios.map((s) => s.id)]));
    // Uno dopo l'altro: ogni run entra in coda con il suo gruppo intero.
    for (const scenario of scenarios) await lab.runScenario(scenario);
    setStarting((current) => new Set([...current].filter((id) => !scenarios.some((s) => s.id === id))));
  };
  const toRun = rows.filter(({ results }) => results.status !== "current" && results.status !== "pending").map(({ scenario }) => scenario);

  const number = (v: number) => v.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 });
  const format: Record<ReplicationKpi, (v: number) => string> = {
    cycle: (v) => formatDuration(v, lang),
    waiting: (v) => formatDuration(v, lang),
    costPerCase: (v) => formatCurrency(v, lang),
    throughput: (v) => t("simulation.results.replicationPerHour", { value: number(v) }),
  };
  const signed = (kpi: ReplicationKpi, v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${format[kpi](Math.abs(v))}`;

  const comparisons = rows.slice(1).map(({ results }) => (asIs ? scenarioDeltas(asIs, results, runs) : null));
  const kinds = new Set(comparisons.flatMap((c) => (c ? Object.values(c.kpis).filter(Boolean).map((d) => (d as ScenarioDelta).kind === "single" ? "single" : c.paired ? "paired" : "independent") : [])));

  return (
    <section className="sim-workspace grid gap-3" data-sim-scenario-workspace aria-labelledby="sim-workspace-title">
      <div className="grid gap-1">
        <h3 id="sim-workspace-title" className="text-sm font-semibold text-foreground">{t("simulation.scenarios.workspace.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("simulation.scenarios.workspace.intro")}</p>
      </div>

      <div className="sim-workspace-seed ui-surface ui-surface-inset">
        <div className="min-w-0">
          <p className="text-xs font-medium text-foreground" data-sim-workspace-seed>{t("simulation.scenarios.workspace.seed", { seed: workspace.seed ?? "—" })}</p>
          <p className="text-xs text-muted-foreground">{t("simulation.scenarios.workspace.seedHint")}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void lab.newSeed()}>
          <Dices aria-hidden className="size-4" />
          {t("simulation.scenarios.workspace.newSeed")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={toRun.length === 0 || starting.size > 0} onClick={() => void run(toRun)}>
          <Play aria-hidden className="size-4" />
          {t("simulation.scenarios.workspace.runAll")}
        </Button>
        {toRun.length === 0 && <span className="text-xs text-muted-foreground">{t("simulation.scenarios.workspace.runAllDone")}</span>}
      </div>
      {lab.workspaceError && <p role="alert" className="sim-scenario-error">{lab.workspaceError}</p>}

      <div className="sim-workspace-table" role="region" tabIndex={0} aria-label={t("simulation.scenarios.workspace.table")}>
        <table>
          <caption>{t("simulation.scenarios.workspace.caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("simulation.scenarios.workspace.scenario")}</th>
              {WORKSPACE_KPIS.map((kpi) => <th key={kpi} scope="col">{t(`simulation.results.replicationKpi.${kpi}`)}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ scenario, results }, index) => {
              const name = scenarioDisplayName(scenario);
              const comparison = index === 0 ? null : comparisons[index - 1];
              const busy = starting.has(scenario.id) || results.status === "pending";
              return (
                <tr key={scenario.id} data-sim-workspace-row={scenario.label}>
                  <th scope="row">
                    <span className="sim-workspace-name"><span className="sim-scenario-label">{scenario.label}</span>{scenario.kind === "alternative" && <span>{scenario.name}</span>}</span>
                    <span className={cn("block text-xs", STATUS_TONE[results.status])}>{t(`simulation.scenarios.workspace.status.${results.status}`)}</span>
                    {results.members.length > 0 && <span className="block text-xs text-muted-foreground">{t("simulation.scenarios.workspace.reps", { count: results.completed.length })}</span>}
                    <span className="sim-workspace-actions">
                      <Button size="sm" variant="ghost" disabled={busy} aria-label={t(results.status === "never" ? "simulation.scenarios.workspace.runScenario" : "simulation.scenarios.workspace.rerunScenario", { name })} onClick={() => void run([scenario])}>
                        <Play aria-hidden className="size-3.5" />
                        {t(results.status === "never" ? "simulation.scenarios.workspace.run" : "simulation.scenarios.workspace.rerun")}
                      </Button>
                      <Button size="sm" variant="ghost" aria-label={t("simulation.scenarios.workspace.editScenario", { name })} onClick={() => openScenario(scenario.kind === "baseline" ? null : scenario.id)}>
                        <Pencil aria-hidden className="size-3.5" />
                        {t("simulation.scenarios.workspace.edit")}
                      </Button>
                      {index > 0 && asIs?.completed.length && results.completed.length ? (
                        <Button size="sm" variant="ghost" aria-label={t("simulation.scenarios.workspace.showOnProcessFor", { name })} onClick={() => showOnProcess(results)}>
                          <ScanEye aria-hidden className="size-3.5" />
                          {t("simulation.scenarios.workspace.showOnProcess")}
                        </Button>
                      ) : null}
                    </span>
                  </th>
                  {WORKSPACE_KPIS.map((kpi) => {
                    const value = scenarioValue(results, kpi);
                    const delta = comparison?.kpis[kpi] ?? null;
                    return (
                      <td key={kpi}>
                        <span className="block tabular-nums text-foreground">
                          {!value ? t("simulation.scenarios.workspace.notRun") : value.interval ? t("simulation.results.replicationValue", { mean: format[kpi](value.interval.mean), half: format[kpi](value.interval.half) }) : format[kpi](value.mean)}
                        </span>
                        {delta && <DeltaLine delta={delta} text={delta.kind === "interval"
                          ? t("simulation.scenarios.workspace.deltaInterval", { delta: signed(kpi, delta.value.delta), half: format[kpi](delta.value.half) })
                          : t("simulation.scenarios.workspace.deltaSingle", { delta: signed(kpi, delta.delta) })} />}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {[...kinds].map((kind) => <p key={kind} className="text-xs text-muted-foreground" data-sim-workspace-method={kind}>{t(`simulation.scenarios.workspace.method.${kind}`)}</p>)}
    </section>
  );
}

function DeltaLine({ delta, text }: { delta: ScenarioDelta; text: string }) {
  const { t } = useTranslation("process");
  const verdict = delta.kind === "interval" ? delta.value.verdict : delta.direction;
  return (
    <span className={cn(
      "block text-xs tabular-nums",
      delta.kind === "interval" && verdict === "better" && "text-[var(--state-success-text)]",
      delta.kind === "interval" && verdict === "worse" && "text-[var(--state-invalid-text)]",
      (delta.kind === "single" || verdict === "unclear" || verdict === "same") && "text-muted-foreground",
    )}>
      {text}
      {delta.kind === "interval" && <> · <strong className="font-medium">{t(`simulation.scenarios.workspace.verdict.${verdict}`)}</strong></>}
    </span>
  );
}
