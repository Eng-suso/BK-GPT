import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, LineChart } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { StatTile } from "@/components/data";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/app/routes";

import type { SimulationRun, SimulationSummary } from "./simulationTypes";
import { SimulationConfigRail } from "./SimulationConfigRail";
import { ReadinessSummary } from "./ReadinessSummary";
import { useScenarioLab } from "./useScenarioLab";
import { SimulationBpmnView, type SimulationNodeOverlay } from "./SimulationBpmnView";
import { SimulationResults } from "./SimulationResultsView";
import {
  formatCurrency,
  formatDuration,
  formatPercent,
  heatBucket,
  readSimulationInsights,
  topBottleneckElementIds,
  withDiagnosticBottleneck,
} from "./simulationResults";
import { useSimulationSection } from "./useSimulationSection";

const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

/**
 * Panoramica — one scrolling page: the active run's KPI snapshot, then the
 * scenario you'll run next (left, with its input-confidence roll-up) beside the
 * model + results (right).
 */
export function SimulationWorkspace(): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();

  const { projectId, processId } = useSimulationSection();
  const lab = useScenarioLab();
  const {
    bpmnXml,
    template,
    templateLoading,
    draft,
    updateDraft,
    provenance,
    confidence,
    activeRun,
    isRunning,
    isPending,
    error,
    handleRun,
  } = lab;

  const [selectedElementId, setSelectedElementId] = React.useState<string | null>(null);

  const summary = (activeRun?.summary as SimulationSummary | null) ?? null;
  const insights = React.useMemo(
    () =>
      withDiagnosticBottleneck(
        readSimulationInsights(activeRun?.result, { bpmnXml }),
        summary,
      ),
    [activeRun?.result, bpmnXml, summary],
  );

  const overlays: SimulationNodeOverlay[] = React.useMemo(() => {
    if (!insights.hasData) return [];
    const badgeIds = new Set(topBottleneckElementIds(insights, 3));
    const maxWait = Math.max(1, ...insights.tasks.map((task) => task.avgWaitingSec));
    return insights.tasks
      .filter((task) => task.elementId)
      .map((task) => ({
        elementId: task.elementId as string,
        waitLabel: formatDuration(task.avgWaitingSec, lang),
        heat: heatBucket(task.avgWaitingSec, maxWait),
        showBadge: badgeIds.has(task.elementId as string),
        isBottleneck: task.elementId === insights.bottleneckElementId,
      }));
  }, [insights, lang]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto pb-4">
      <RunSnapshot
        run={activeRun}
        insights={insights}
        isPending={isPending}
        lang={lang}
        onOpenReplay={() =>
          activeRun &&
          navigate(
            ROUTES.projects.simulation(projectId, processId, `replay/${activeRun.id}`),
          )
        }
        onOpenDashboard={() =>
          activeRun &&
          navigate(
            ROUTES.projects.simulation(projectId, processId, `dashboard/${activeRun.id}`),
          )
        }
      />

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(320px,0.82fr)_minmax(0,1.18fr)]">
        <div className="flex flex-col gap-4 self-start">
          <ReadinessSummary
            dense
            confidence={confidence}
            provenance={provenance}
            onReview={() =>
              navigate(ROUTES.projects.simulation(projectId, processId, "scenario"))
            }
          />
          <SimulationConfigRail
            embedded
            template={template}
            templateLoading={templateLoading}
            draft={draft}
            onDraftChange={updateDraft}
            isRunning={isRunning}
            error={error}
            onRun={() => void handleRun()}
            focusElementId={selectedElementId}
            provenance={confidence}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <section
            aria-label={t("simulation.diagram.title")}
            className="flex min-h-[460px] flex-col overflow-hidden rounded-lg border border-border bg-card"
          >
            <header className="border-b border-border px-4 py-2.5">
              <p className="eyebrow">{t("simulation.diagram.title")}</p>
            </header>
            {bpmnXml ? (
              <SimulationBpmnView
                className="min-h-0 flex-1"
                bpmnXml={bpmnXml}
                overlays={overlays}
                selectedElementId={selectedElementId}
                onSelectElement={setSelectedElementId}
              />
            ) : (
              <div className="p-4">
                <EmptyState variant="inline" title={t("simulation.diagram.noModel")} />
              </div>
            )}
          </section>

          <section
            aria-label={t("simulation.output.eyebrow")}
            className="rounded-lg border border-border bg-card"
          >
            <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
              <p className="eyebrow">{t("simulation.results.summary")}</p>
              {activeRun && (
                <StatusIndicator
                  tone={RUN_TONE[activeRun.status]}
                  label={t(`simulation.status.${activeRun.status}`, {
                    defaultValue: activeRun.status,
                  })}
                />
              )}
            </header>
            <div className="p-4">
              {!activeRun ? (
                <EmptyState variant="inline" title={t("simulation.empty")} />
              ) : activeRun.error ? (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium leading-relaxed text-destructive"
                >
                  {activeRun.error}
                </p>
              ) : isPending ? (
                <EmptyState variant="inline" title={t("simulation.running")} />
              ) : (
                <SimulationResults
                  insights={insights}
                  selectedElementId={selectedElementId}
                  onSelectElement={setSelectedElementId}
                />
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //

type RunSnapshotProps = {
  run: SimulationRun | null;
  insights: ReturnType<typeof readSimulationInsights>;
  isPending: boolean;
  lang: "it" | "en";
  onOpenReplay: () => void;
  onOpenDashboard: () => void;
};

function RunSnapshot({
  run,
  insights,
  isPending,
  lang,
  onOpenReplay,
  onOpenDashboard,
}: RunSnapshotProps): React.JSX.Element {
  const { t } = useTranslation("process");

  if (!run) {
    return (
      <section className="rounded-lg border border-border bg-card p-4">
        <EmptyState
          variant="inline"
          title={t("simulation.empty")}
          description={t("simulation.overview.noRunHint")}
        />
      </section>
    );
  }

  const busiest = [...insights.resources].sort(
    (a, b) => b.utilizationPct - a.utilizationPct,
  )[0];

  return (
    <section className="rounded-lg border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="eyebrow">{t("simulation.output.eyebrow")}</p>
          <h2 className="mt-0.5 truncate text-sm font-semibold text-foreground">
            {run.scenario_name}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <StatusIndicator
            tone={RUN_TONE[run.status]}
            label={t(`simulation.status.${run.status}`, { defaultValue: run.status })}
          />
          {run.status === "completed" && (
            <>
              <Button type="button" size="sm" variant="outline" onClick={onOpenReplay}>
                <Activity aria-hidden className="size-3.5" />
                {t("simulation.section.nav.replay")}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={onOpenDashboard}>
                <LineChart aria-hidden className="size-3.5" />
                {t("simulation.section.nav.dashboard")}
              </Button>
            </>
          )}
        </div>
      </header>

      {isPending ? (
        <div className="p-4">
          <EmptyState variant="inline" title={t("simulation.running")} />
        </div>
      ) : !insights.hasData ? (
        <div className="p-4">
          <EmptyState variant="inline" title={t("simulation.results.noData")} />
        </div>
      ) : (
        <div className="p-4">
          {insights.bottleneck && (
            <p
              className={cn(
                "mb-3 flex items-start gap-2 rounded-md border px-3 py-2 text-xs leading-relaxed text-foreground",
              )}
              style={{
                borderColor: "var(--sim-bottleneck-border)",
                background: "var(--sim-bottleneck-surface)",
              }}
            >
              <span
                aria-hidden
                className="mt-1 size-1.5 shrink-0 rounded-full"
                style={{ background: "var(--color-status-warning)" }}
              />
              <span>
                <strong className="font-semibold">
                  {t("simulation.results.bottleneck")}: {insights.bottleneck.name}
                </strong>
                {" — "}
                {t("simulation.results.bottleneckDetail", {
                  wait: formatDuration(insights.bottleneck.avgWaitingSec, lang),
                  share: formatPercent(insights.bottleneck.waitingShare),
                })}
              </span>
            </p>
          )}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            <StatTile
              label={t("simulation.results.cases")}
              value={new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US").format(
                insights.casesCompleted,
              )}
            />
            <StatTile
              label={t("simulation.results.cycleTime")}
              value={formatDuration(insights.avgCycleSec, lang)}
              hint={t("simulation.results.waitingShare", {
                share: formatPercent(insights.waitingShare),
              })}
            />
            <StatTile
              label={t("simulation.results.waitingTime")}
              value={formatDuration(insights.avgWaitingSec, lang)}
            />
            <StatTile
              label={t("simulation.results.processingTime")}
              value={formatDuration(insights.avgProcessingSec, lang)}
            />
            <StatTile
              label={t("simulation.results.costPerCase")}
              value={formatCurrency(insights.avgCostPerCase, lang)}
              hint={t("simulation.results.totalCost", {
                total: formatCurrency(insights.totalCost, lang),
              })}
            />
            {busiest && (
              <StatTile
                label={t("simulation.results.busiestResource")}
                value={`${busiest.utilizationPct}%`}
                hint={busiest.name}
                tone={
                  busiest.utilizationPct >= 95
                    ? "danger"
                    : busiest.utilizationPct >= 85
                      ? "warning"
                      : "neutral"
                }
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
