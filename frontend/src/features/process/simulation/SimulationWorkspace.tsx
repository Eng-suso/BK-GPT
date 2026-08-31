import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Activity, LineChart } from "lucide-react";

import { HttpError } from "@/lib/http";
import { EmptyState } from "@/components/feedback";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { StatTile } from "@/components/data";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/app/routes";

import { useBpmnModelQuery } from "../api";
import {
  fetchScenarioTemplate,
  getProsimosSimulationRun,
  runProsimosSimulation,
} from "./simulationApi";
import type {
  ScenarioTemplate,
  SimulationRun,
  SimulationSummary,
} from "./simulationTypes";
import { SimulationConfigRail } from "./SimulationConfigRail";
import {
  loadScenarioDraft,
  saveScenarioDraft,
  scenarioToInput,
  seedDraftFromTemplate,
  type ScenarioDraft,
} from "./simulationScenario";
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
import { resolveActiveRun, useSimulationSection } from "./useSimulationSection";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;
const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Panoramica — one scrolling page: the active run's KPI snapshot, then the
 * scenario you'll run next (left) beside the model + results (right).
 */
export function SimulationWorkspace(): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { projectId, processId, process, runs: sectionRuns, refetchRuns } =
    useSimulationSection();
  const modelQuery = useBpmnModelQuery(process.bpmnModelId);
  const bpmnXml = modelQuery.data?.xml ?? null;

  const [pickedRunId, setPickedRunId] = React.useState<number | null>(null);
  const [polledRun, setPolledRun] = React.useState<SimulationRun | null>(null);
  const [isRunning, setIsRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedElementId, setSelectedElementId] = React.useState<string | null>(null);
  const mountedRef = React.useRef(true);

  const activeRun: SimulationRun | null = React.useMemo(() => {
    if (polledRun) return polledRun;
    if (pickedRunId != null) {
      return sectionRuns.find((r) => r.id === pickedRunId) ?? null;
    }
    return resolveActiveRun(sectionRuns, undefined);
  }, [polledRun, pickedRunId, sectionRuns]);

  const [storedDraft, setStoredDraft] = React.useState<ScenarioDraft>(() =>
    loadScenarioDraft(process.bpmnModelId),
  );

  const templateQuery = useQuery<ScenarioTemplate>({
    queryKey: ["workspace", "simulation-template", process.bpmnModelId],
    queryFn: () => fetchScenarioTemplate(process.bpmnModelId, null),
    enabled: bpmnXml !== null,
    staleTime: 60_000,
  });
  const template = templateQuery.data ?? null;
  const templateLoading = templateQuery.isLoading && bpmnXml !== null;

  const draft = React.useMemo(
    () => (template ? seedDraftFromTemplate(storedDraft, template) : storedDraft),
    [storedDraft, template],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const updateDraft = React.useCallback(
    (next: ScenarioDraft) => {
      setStoredDraft(next);
      saveScenarioDraft(process.bpmnModelId, next);
    },
    [process.bpmnModelId],
  );

  const syncSection = React.useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["workspace", "simulation-runs", process.bpmnModelId],
    });
    refetchRuns();
  }, [queryClient, process.bpmnModelId, refetchRuns]);

  const pollRun = React.useCallback(
    async (runId: number) => {
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      while (Date.now() < deadline) {
        await delay(POLL_INTERVAL_MS);
        if (!mountedRef.current) return;
        let latest: SimulationRun;
        try {
          latest = await getProsimosSimulationRun(runId);
        } catch (err) {
          if (mountedRef.current) setError(readError(err));
          return;
        }
        if (!mountedRef.current) return;
        setPolledRun(latest);
        if (latest.status !== "pending") {
          syncSection();
          setPickedRunId(latest.id);
          setPolledRun(null);
          if (latest.status === "failed" && latest.error) setError(latest.error);
          return;
        }
      }
      setError(t("simulation.timeout"));
    },
    [t, syncSection],
  );

  async function handleRun() {
    setIsRunning(true);
    setError(null);
    setSelectedElementId(null);
    try {
      const run = await runProsimosSimulation(process.bpmnModelId, {
        ...scenarioToInput(draft, bpmnXml),
        idempotencyKey:
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${process.bpmnModelId}-${Date.now()}`,
      });
      setPolledRun(run);
      syncSection();
      if (run.status === "pending") await pollRun(run.id);
      else setPickedRunId(run.id);
    } catch (err) {
      setError(readError(err));
    } finally {
      if (mountedRef.current) setIsRunning(false);
    }
  }

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

  const isPending = activeRun?.status === "pending";

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
            ROUTES.projects.simulation(
              projectId,
              processId,
              `replay/${activeRun.id}`,
            ),
          )
        }
        onOpenDashboard={() =>
          activeRun &&
          navigate(
            ROUTES.projects.simulation(
              projectId,
              processId,
              `dashboard/${activeRun.id}`,
            ),
          )
        }
      />

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(320px,0.82fr)_minmax(0,1.18fr)]">
        <div className="self-start">
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
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onOpenDashboard}
              >
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

function readError(error: unknown): string {
  if (error instanceof HttpError) {
    const body = error.body;
    if (body && typeof body === "object") {
      if ("detail" in body && typeof body.detail === "string") return body.detail;
      const nested = (body as { error?: { message?: unknown } }).error;
      if (nested && typeof nested.message === "string") return nested.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Simulazione non riuscita.";
}
