import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowRight, Sparkles, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { Meter } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import { ROUTES } from "@/app/routes";

import { fetchSimulationExperiments } from "../simulationApi";
import type { Experiment, SimulationSummary } from "../simulationTypes";
import { useScenarioLab } from "../useScenarioLab";
import { useSimulationSection } from "../useSimulationSection";
import { formatDuration, formatPercent } from "../simulationResults";

const FACTOR_ORDER = [
  "waitingContribution",
  "cycleContribution",
  "utilization",
  "queueGrowth",
  "casesAffected",
  "persistence",
] as const;

export function InsightsPage(): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();
  const { projectId, processId } = useSimulationSection();

  const lab = useScenarioLab();
  const { activeRun, draft, updateDraft, confidence } = lab;
  const summary = (activeRun?.summary as SimulationSummary | null) ?? null;

  const query = useQuery({
    queryKey: ["workspace", "simulation-experiments", activeRun?.id],
    queryFn: () => fetchSimulationExperiments(activeRun!.id),
    enabled: activeRun?.status === "completed" && Boolean(summary),
    staleTime: 60_000,
  });
  const report = query.data ?? null;

  if (!activeRun) {
    return <Gate title={t("simulation.insights.noRun")} description={t("simulation.insights.noRunHint")} />;
  }
  if (activeRun.status === "pending") return <Gate title={t("simulation.running")} />;
  if (!summary) return <Gate title={t("simulation.insights.noData")} />;

  const lowConfidence =
    confidence.readiness.overall === "low" ||
    (report?.bottleneck_el != null &&
      (confidence.activities[report.bottleneck_el]?.confidence === "low" ||
        confidence.gateways[report.bottleneck_el]?.confidence === "low"));

  const applyExperiment = (exp: Experiment) => {
    const servingId = exp.target_el
      ? draft.tasks[exp.target_el]?.resourceId
      : draft.resources[0]?.id;
    const targetId =
      draft.resources.find(
        (r) => r.name.toLowerCase() === exp.pool_name.toLowerCase(),
      )?.id ??
      servingId ??
      draft.resources[0]?.id;
    updateDraft({
      ...draft,
      scenarioName: t("simulation.insights.scenarioName", {
        base: draft.scenarioName,
        pool: exp.pool_name,
      }),
      resources: draft.resources.map((r) =>
        r.id === targetId ? { ...r, amount: r.amount + 1 } : r,
      ),
    });
    navigate(ROUTES.projects.simulation(projectId, processId, "scenario"));
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-4">
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles aria-hidden className="size-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-foreground">
              {t("simulation.insights.title")}
            </h2>
          </div>
          {report?.bottleneck_name && (
            <StatusIndicator tone="warning" label={report.bottleneck_name} />
          )}
        </div>

        {report?.bottleneck_name ? (
          <>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {t("simulation.insights.diagnostic", {
                name: report.bottleneck_name,
                wait: formatDuration(
                  bottleneckWait(summary, report.bottleneck_el),
                  lang,
                ),
                share: formatPercent(summary.waiting?.share ?? 0),
              })}
            </p>
            <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
              {FACTOR_ORDER.filter((k) => k in (report.factors ?? {})).map((k) => (
                <li key={k} className="grid gap-1">
                  <span className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    {t(`simulation.heatmap.factor.${k}`)}
                    <span className="tabular-nums">
                      {Math.round((report.factors[k] ?? 0) * 100)}%
                    </span>
                  </span>
                  <Meter
                    value={Math.round((report.factors[k] ?? 0) * 100)}
                    tone="warning"
                    showValue={false}
                    height={4}
                  />
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">
            {t("simulation.insights.noBottleneck")}
          </p>
        )}
      </section>

      {lowConfidence && (
        <p className="flex items-start gap-2 rounded-md border border-[var(--amber-400,#fbbf24)] bg-[var(--sim-bottleneck-surface)] px-3 py-2 text-xs leading-relaxed text-foreground">
          <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-700)]" />
          {t("simulation.insights.lowConfidenceCaveat")}
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {(report?.experiments ?? []).map((exp, i) => (
          <ExperimentCard key={i} exp={exp} onApply={() => applyExperiment(exp)} />
        ))}
        {report && report.experiments.length === 0 && (
          <section className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">
              {t("simulation.insights.noExperiment")}
            </p>
          </section>
        )}
      </div>
    </div>
  );
}

function ExperimentCard({
  exp,
  onApply,
}: {
  exp: Experiment;
  onApply: () => void;
}) {
  const { t } = useTranslation("process");
  const cyclePct = exp.estimate.cycle_pct;
  const costPct = exp.estimate.cost_pct;
  return (
    <section className="flex flex-col rounded-lg border border-border bg-card p-4">
      <p className="eyebrow">{t("simulation.insights.experimentKind.add_resource")}</p>
      <h3 className="mt-1 text-sm font-semibold text-foreground">
        {t("simulation.insights.addResourceTitle", {
          pool: exp.pool_name,
          from: exp.from_amount,
          to: exp.to_amount,
        })}
      </h3>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        {exp.rationale}
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-2">
        <Estimate
          label={t("simulation.results.cycleTime")}
          value={signedPct(cyclePct)}
          tone={cyclePct < 0 ? "good" : "neutral"}
        />
        <Estimate
          label={t("simulation.results.costPerCase")}
          value={signedPct(costPct)}
          tone={costPct > 0 ? "bad" : "neutral"}
        />
      </dl>
      <p className="mt-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        {t("simulation.insights.estimateNote")}
      </p>

      <Button type="button" size="sm" className="mt-3 gap-1.5 self-start" onClick={onApply}>
        {t("simulation.insights.createScenario")}
        <ArrowRight aria-hidden className="size-3.5" />
      </Button>
    </section>
  );
}

function Estimate({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "good" | "bad" | "neutral";
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd
        className="m-0 text-sm font-semibold tabular-nums"
        style={{
          color:
            tone === "good"
              ? "var(--color-status-success)"
              : tone === "bad"
                ? "var(--color-status-danger)"
                : "var(--color-text-primary)",
        }}
      >
        {value}
      </dd>
    </div>
  );
}

function signedPct(fraction: number): string {
  const pct = Math.round(fraction * 100);
  if (pct === 0) return "≈ 0%";
  return `${pct > 0 ? "+" : "−"}${Math.abs(pct)}%`;
}

function bottleneckWait(summary: SimulationSummary, el: string | null | undefined): number {
  if (!el) return 0;
  const row = (summary.byActivity as Array<Record<string, unknown>> | undefined)?.find(
    (a) => a.el === el,
  );
  return Number((row?.wait as { avg?: number } | undefined)?.avg ?? 0);
}

function Gate({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <EmptyState icon={Sparkles} title={title} description={description} />
    </div>
  );
}
