import React from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { ROUTES } from "@/app/routes";
import { useProjectQuery } from "@/features/projects/api";

import { useBpmnModelQuery } from "../api";
import { listProsimosSimulationRuns } from "./simulationApi";
import { formatRunOption, SimulationSectionContext } from "./useSimulationSection";

/** Sub-screens, in order — each is a nested route segment under `.../simulation`. */
const TABS = [
  "overview",
  "scenario",
  "replay",
  "dashboard",
  "compare",
  "heatmap",
  "insights",
] as const;
type Tab = (typeof TABS)[number];

const RUN_SCOPED = new Set<Tab>(["replay", "dashboard", "heatmap", "insights"]);

/** Pull `<sub>` and optional numeric `<runId>` out of `.../simulation/<sub>/<runId>`. */
function readPath(pathname: string): { sub: Tab; runId: number | null } {
  const parts = pathname.split("/").filter(Boolean);
  const idx = parts.indexOf("simulation");
  const raw = (idx >= 0 && parts[idx + 1]) || "overview";
  const sub = (TABS as readonly string[]).includes(raw) ? (raw as Tab) : "overview";
  const rid = idx >= 0 ? parts[idx + 2] : undefined;
  return { sub, runId: rid && /^\d+$/.test(rid) ? Number(rid) : null };
}

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
  });
  const runs = React.useMemo(() => runsQ.data ?? [], [runsQ.data]);

  const { sub, runId } = readPath(location.pathname);
  const activeRunId =
    runId ??
    runs.find((r) => r.status === "completed")?.id ??
    runs[0]?.id ??
    null;

  const goToTab = React.useCallback(
    (next: string) => {
      const scoped = RUN_SCOPED.has(next as Tab) && activeRunId != null;
      navigate(
        ROUTES.projects.simulation(
          projectId,
          processId,
          scoped ? `${next}/${activeRunId}` : next,
        ),
      );
    },
    [navigate, projectId, processId, activeRunId],
  );

  const switchRun = React.useCallback(
    (value: string) => {
      const target = RUN_SCOPED.has(sub) ? sub : "replay";
      navigate(
        ROUTES.projects.simulation(projectId, processId, `${target}/${value}`),
      );
    },
    [navigate, projectId, processId, sub],
  );

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
  };

  return (
    <SimulationSectionContext.Provider value={contextValue}>
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-col gap-3 px-7 pb-2 pt-6">
          <PageHeader
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
            meta={
              <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {t("simulation.section.title")}
              </span>
            }
            actions={
              <div className="flex items-center gap-2">
                {runs.length > 0 && (
                  <Select
                    value={activeRunId != null ? String(activeRunId) : undefined}
                    onValueChange={switchRun}
                  >
                    <SelectTrigger size="sm" className="w-[248px]">
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
                  onClick={() =>
                    navigate(ROUTES.projects.process(project.id, process.id))
                  }
                >
                  <ArrowLeft aria-hidden className="size-4" />
                  {t("simulation.section.back")}
                </Button>
              </div>
            }
          />

          <Tabs value={sub} onValueChange={goToTab}>
            <TabsList variant="line" className="max-w-full overflow-x-auto">
              {TABS.map((tab) => (
                <TabsTrigger key={tab} value={tab}>
                  {t(`simulation.section.nav.${tab}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="min-h-0 flex-1 px-7 pb-7">
          <Outlet />
        </div>
      </div>
    </SimulationSectionContext.Provider>
  );
}
