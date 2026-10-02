import React from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { ROUTES } from "@/app/routes";
import { useProjectQuery } from "@/features/projects/api";

import "./dashboard/dashboard.css";
import { useBpmnModelQuery } from "../api";
import { SimulationStudio } from "./SimulationStudio";
import { ReplaySession } from "./replay/ReplaySession";
import { listProsimosSimulationRuns } from "./simulationApi";
import { formatRunOption, SimulationSectionContext, type SimulationPanel, type AnalysisView } from "./useSimulationSection";

const PANELS = ["scenario", "overview", "compare", "heatmap", "insights", "widget", "activity"] as const;

/**
 * Renders the simulation workspace layout with process navigation, run selection, and nested route content.
 *
 * @returns The simulation workspace layout.
 */
export function SimulationLayout(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();
  const location = useLocation();

  const projectQ = useProjectQuery(projectId);
  const project = projectQ.data;
  const process = project?.processItems.find((p) => p.id === processId);

  const modelQ = useBpmnModelQuery(process?.bpmnModelId ?? "", {
    enabled: Boolean(process?.bpmnModelId),
  });

  const runsQ = useQuery({
    queryKey: ["workspace", "simulation-runs", process?.bpmnModelId],
    queryFn: () => listProsimosSimulationRuns(process!.bpmnModelId),
    enabled: Boolean(process?.bpmnModelId),
    refetchInterval: (query) => query.state.data?.some((run) => run.status === "pending") ? 2000 : false,
  });
  const runs = React.useMemo(() => runsQ.data ?? [], [runsQ.data]);

  const parts = location.pathname.split("/").filter(Boolean);
  const index = parts.indexOf("simulation");
  const section = parts[index + 1] ?? "workspace";
  const params = new URLSearchParams(location.search);
  const requestedId = Number(parts[index + 2] ?? params.get("run"));
  const activeRunId = Number.isFinite(requestedId) && requestedId > 0
    ? requestedId : runs.find((run) => run.status === "completed")?.id ?? runs[0]?.id ?? null;
  const requestedPanel = params.get("panel") ?? (section === "workspace" || section === "replay" || section === "dashboard" ? null : section);
  const panel = PANELS.includes(requestedPanel as SimulationPanel) ? requestedPanel as SimulationPanel : null;
  const requestedView = params.get("view");
  const analysisView: AnalysisView = ["replay", "final", "compare", "heatmap"].includes(requestedView ?? "") ? requestedView as AnalysisView
    : panel === "compare" ? "compare" : panel === "heatmap" ? "heatmap" : panel === "overview" || panel === "insights" ? "final" : "replay";
  const panelRef = React.useRef(panel);
  React.useEffect(() => { panelRef.current = panel; }, [panel]);
  const selectionScope = `${projectId}:${processId}:${activeRunId}`;
  const [selection, setSelection] = React.useState<{ scope: string; id: string | null }>({ scope: "", id: null });
  const selectedElementId = selection.scope === selectionScope ? selection.id : null;
  const selectElement = React.useCallback((id: string | null) => setSelection({ scope: selectionScope, id }), [selectionScope]);
  const navigateWorkspace = React.useCallback((nextPanel: SimulationPanel | null, id: number | null = activeRunId) => {
    const query = new URLSearchParams(location.search);
    query.delete("run");
    query.set("view", nextPanel === "compare" ? "compare" : nextPanel === "heatmap" ? "heatmap" : nextPanel === "overview" || nextPanel === "insights" ? "final" : analysisView);
    if (nextPanel) query.set("panel", nextPanel); else query.delete("panel");
    const search = query.toString();
    navigate(ROUTES.projects.simulation(projectId, processId, `workspace${id != null ? `/${id}` : ""}`) + (search ? `?${search}` : ""));
  }, [activeRunId, analysisView, location.search, navigate, processId, projectId]);
  const openPanel = React.useCallback((next: SimulationPanel | null) => { panelRef.current = next; navigateWorkspace(next); }, [navigateWorkspace]);
  const selectRun = React.useCallback((id: number) => { setSelection({ scope: "", id: null }); navigateWorkspace(panelRef.current === "widget" || panelRef.current === "activity" ? null : panelRef.current, id); }, [navigateWorkspace]);
  const [inspectedWidgetId, setInspectedWidgetId] = React.useState<string | null>(null);
  const inspectWidget = (id: string | null) => { setInspectedWidgetId(id); openPanel(id ? "widget" : null); };
  const setAnalysisView = (view: AnalysisView) => {
    const query = new URLSearchParams(location.search); query.set("view", view); query.delete("panel");
    navigate(ROUTES.projects.simulation(projectId, processId, `workspace${activeRunId != null ? `/${activeRunId}` : ""}`) + `?${query}`);
  };
  const switchRun = (value: string) => selectRun(Number(value));

  if (projectQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6">
        <Skeleton className="h-4 w-56" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-9 w-96" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    );
  }

  if (projectQ.isError || !project || !process) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorState
          description={
            projectQ.isError ? t("state.loadError") : t("state.processNotFound")
          }
          onRetry={projectQ.isError ? () => void projectQ.refetch() : undefined}
          action={
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(ROUTES.projects.detail(projectId))}
            >
              {t("actions.backToProject")}
            </Button>
          }
        />
      </div>
    );
  }

  const contextValue = {
    projectId,
    processId,
    project,
    process,
    bpmnXml: modelQ.data?.xml ?? null,
    runs,
    runsLoading: runsQ.isLoading,
    refetchRuns: () => void runsQ.refetch(),
    activeRunId, selectRun, selectedElementId, selectElement, analysisView, setAnalysisView, panel, openPanel, inspectedWidgetId, inspectWidget,
  };

  return (
    <SimulationSectionContext.Provider value={contextValue}>
      <div className="sim-studio-shell flex h-full min-h-0 flex-col">
        <div className="flex shrink-0 flex-col gap-2 px-4 pb-2 pt-3">
          <PageHeader
            compact
            className="sim-studio-page-header"
            breadcrumbs={[
              { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
              { label: project.name, to: ROUTES.projects.detail(project.id) },
              {
                label: process.name,
                to: ROUTES.projects.process(project.id, process.id),
              },
              { label: t("simulation.section.title") },
            ]}
            title={process.name}
            actions={
              <div className="sim-studio-run-actions flex max-w-full flex-wrap items-center gap-2">
                {runs.length > 0 && (
                  <Select
                    value={activeRunId != null ? String(activeRunId) : undefined}
                    onValueChange={switchRun}
                  >
                    <SelectTrigger size="sm" className="w-[280px] max-w-full" aria-label={t("simulation.section.runSwitcher")}>
                      <SelectValue
                        placeholder={t("simulation.section.runSwitcher")}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {runs.map((run) => (
                        <SelectItem key={run.id} value={String(run.id)}>
                          {formatRunOption(run, lang)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="sim-studio-return"
                  aria-label={t("simulation.section.back")}
                  onClick={() =>
                    navigate(ROUTES.projects.process(project.id, process.id))
                  }
                >
                  <ArrowLeft aria-hidden className="size-4" />
                  <span>{t("simulation.section.back")}</span>
                </Button>
              </div>
            }
          />

        </div>

        <div className="min-h-0 flex-1 px-4 pb-4">
          <ReplaySession
            runId={runs.find((run) => run.id === activeRunId)?.status === "completed" ? activeRunId : null}
            enabled={true}
          >
            <SimulationStudio />
          </ReplaySession>
        </div>
      </div>
    </SimulationSectionContext.Provider>
  );
}
