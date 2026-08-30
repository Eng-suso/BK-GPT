import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { HttpError } from "@/lib/http";
import { EmptyState } from "@/components/feedback";
import { cn } from "@/lib/utils";
import type { ProjectProcess } from "../../contracts/workspace";
import { useBpmnModelQuery } from "./api";
import {
  fetchScenarioTemplate,
  getProsimosSimulationRun,
  listProsimosSimulationRuns,
  runProsimosSimulation,
} from "./simulationApi";
import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";
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
import { formatDuration, readSimulationInsights } from "./simulationResults";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

type SimulationWorkspaceProps = {
  process: ProjectProcess;
  currentBpmnXml: string | null;
};

export function SimulationWorkspace({
  process,
  currentBpmnXml,
}: SimulationWorkspaceProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const modelQuery = useBpmnModelQuery(process.bpmnModelId);
  const bpmnXml = currentBpmnXml ?? modelQuery.data?.xml ?? null;

  const [runs, setRuns] = React.useState<SimulationRun[]>([]);
  const [activeRun, setActiveRun] = React.useState<SimulationRun | null>(null);
  const [isRunning, setIsRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedElementId, setSelectedElementId] = React.useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = React.useState(false);

  const [storedDraft, setStoredDraft] = React.useState<ScenarioDraft>(() =>
    loadScenarioDraft(process.bpmnModelId),
  );
  const mountedRef = React.useRef(true);

  const templateQuery = useQuery<ScenarioTemplate>({
    queryKey: ["workspace", "simulation-template", process.bpmnModelId, currentBpmnXml],
    queryFn: () => fetchScenarioTemplate(process.bpmnModelId, currentBpmnXml),
    enabled: bpmnXml !== null,
    staleTime: 60_000,
  });
  const template: ScenarioTemplate | null = templateQuery.data ?? null;
  const templateLoading = templateQuery.isLoading && bpmnXml !== null;

  // Editable draft = stored user edits with template defaults filled in.
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

  // Load existing runs.
  React.useEffect(() => {
    let cancelled = false;
    void listProsimosSimulationRuns(process.bpmnModelId)
      .then((next) => {
        if (cancelled) return;
        setRuns(next);
        setActiveRun((cur) => cur ?? next[0] ?? null);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof HttpError && err.status === 404) {
          setRuns([]);
          return;
        }
        setError(readError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [process.bpmnModelId]);

  const updateDraft = React.useCallback(
    (next: ScenarioDraft) => {
      setStoredDraft(next);
      saveScenarioDraft(process.bpmnModelId, next);
    },
    [process.bpmnModelId],
  );

  const upsertRun = React.useCallback((run: SimulationRun) => {
    setRuns((cur) => [run, ...cur.filter((r) => r.id !== run.id)].sort((a, b) => b.id - a.id));
    setActiveRun((cur) => (cur && cur.id !== run.id ? cur : run));
  }, []);

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
        upsertRun(latest);
        setActiveRun(latest);
        if (latest.status !== "pending") {
          if (latest.status === "failed" && latest.error) setError(latest.error);
          return;
        }
      }
      setError(t("simulation.timeout"));
    },
    [t, upsertRun],
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
      upsertRun(run);
      setActiveRun(run);
      if (run.status === "pending") await pollRun(run.id);
    } catch (err) {
      setError(readError(err));
    } finally {
      if (mountedRef.current) setIsRunning(false);
    }
  }

  function selectElement(elementId: string | null) {
    setSelectedElementId(elementId);
    if (elementId) setRailCollapsed(false);
  }

  const insights = React.useMemo(
    () => readSimulationInsights(activeRun?.result, { bpmnXml }),
    [activeRun?.result, bpmnXml],
  );

  const overlays: SimulationNodeOverlay[] = React.useMemo(() => {
    if (!insights.hasData) return [];
    const singleResourceUtil =
      insights.resources.length === 1 ? insights.resources[0].utilizationPct : undefined;
    return insights.tasks
      .filter((task) => task.elementId)
      .map((task) => ({
        elementId: task.elementId as string,
        waitLabel: formatDuration(task.avgWaitingSec, lang),
        utilizationPct: singleResourceUtil,
        isBottleneck: task.elementId === insights.bottleneckElementId,
      }));
  }, [insights, lang]);

  const isPending = activeRun?.status === "pending";

  return (
    <div
      className={cn(
        "grid h-full min-h-0 gap-3 overflow-hidden p-3",
        railCollapsed
          ? "grid-cols-1 xl:grid-cols-[40px_minmax(0,1fr)_minmax(340px,380px)]"
          : "grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)_minmax(340px,380px)]",
      )}
    >
      <SimulationConfigRail
        template={template}
        templateLoading={templateLoading}
        draft={draft}
        onDraftChange={updateDraft}
        isRunning={isRunning}
        error={error}
        runs={runs}
        activeRunId={activeRun?.id ?? null}
        onRun={() => void handleRun()}
        onSelectRun={(run) => {
          setActiveRun(run);
          setSelectedElementId(null);
        }}
        focusElementId={selectedElementId}
        collapsed={railCollapsed}
        onToggleCollapsed={() => setRailCollapsed((v) => !v)}
      />

      <section
        aria-label={t("simulation.diagram.title")}
        className="flex min-h-[420px] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm xl:min-h-0"
      >
        {bpmnXml ? (
          <SimulationBpmnView
            className="h-full"
            bpmnXml={bpmnXml}
            overlays={overlays}
            selectedElementId={selectedElementId}
            onSelectElement={selectElement}
          />
        ) : (
          <div className="p-3.5">
            <EmptyState variant="inline" title={t("simulation.diagram.noModel")} />
          </div>
        )}
      </section>

      <section
        aria-label={t("simulation.output.eyebrow")}
        className="flex min-h-[320px] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm xl:min-h-0"
      >
        <header className="flex min-h-[52px] items-center border-b border-border px-3.5 py-2.5">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {t("simulation.output.eyebrow")}
            </p>
            <h3 className="mt-0.5 truncate text-sm font-semibold text-foreground">
              {activeRun?.scenario_name ?? t("simulation.output.title")}
            </h3>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-3.5">
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
            <div className="grid content-start gap-3">
              <SimulationResults
                insights={insights}
                selectedElementId={selectedElementId}
                onSelectElement={selectElement}
              />
              <details className="rounded-md border border-border bg-muted/40 p-2.5">
                <summary className="cursor-pointer text-xs font-semibold text-foreground">
                  {t("simulation.jsonSummary")}
                </summary>
                <pre className="mt-2.5 max-h-[320px] overflow-auto rounded-md border border-border bg-card p-2.5 font-mono text-[11px] leading-relaxed text-foreground/80">
                  {JSON.stringify(activeRun.result, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      </section>
    </div>
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
