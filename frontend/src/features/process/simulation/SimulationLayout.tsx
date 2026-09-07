import React from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChartNoAxesCombined } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
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
const PRIMARY_TABS: Tab[] = ["scenario", "overview", "compare"];
const ANALYSIS_TABS: Tab[] = ["dashboard", "replay", "heatmap", "insights"];

/**
 * Parses the simulation sub-route and optional run identifier from a pathname.
 *
 * @param pathname - The URL pathname containing the simulation route
 * @returns The recognized tab and numeric run ID, or `null` when the run ID is missing or invalid
 */
function readPath(pathname: string): { sub: Tab; runId: number | null } {
  const parts = pathname.split("/").filter(Boolean);
  const idx = parts.indexOf("simulation");
  const raw = (idx >= 0 && parts[idx + 1]) || "overview";
  const sub = (TABS as readonly string[]).includes(raw) ? (raw as Tab) : "overview";
  const rid = idx >= 0 ? parts[idx + 2] : undefined;
  return { sub, runId: rid && /^\d+$/.test(rid) ? Number(rid) : null };
}

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
        <div className="flex shrink-0 flex-col gap-2 px-4 pb-2 pt-3">
          <PageHeader
            compact
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
              <div className="flex max-w-full flex-wrap items-center gap-2">
                {runs.length > 0 && (
                  <Select
                    value={activeRunId != null ? String(activeRunId) : undefined}
                    onValueChange={switchRun}
                  >
                    <SelectTrigger size="sm" className="w-[200px] max-w-full" aria-label={t("simulation.section.runSwitcher")}>
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

          <nav aria-label={t("simulation.section.navLabel")} className="flex min-w-0 gap-1 border-b border-border">
              {PRIMARY_TABS.map((tab) => (
                <button type="button" key={tab} onClick={() => goToTab(tab)} aria-current={sub === tab ? "page" : undefined} className={`shrink-0 whitespace-nowrap px-2 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring sm:px-3 ${sub === tab ? "border-b-2 border-primary font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  {t(`simulation.section.nav.${tab}`)}
                </button>
              ))}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" aria-label={t("simulation.workspace.analysis")} aria-current={ANALYSIS_TABS.includes(sub) ? "page" : undefined} className={`flex min-w-0 items-center gap-1 px-2 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring sm:px-3 ${ANALYSIS_TABS.includes(sub) ? "border-b-2 border-primary font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  <ChartNoAxesCombined className="size-4 shrink-0 sm:hidden" />
                  <span className="hidden truncate sm:inline">{t(ANALYSIS_TABS.includes(sub) ? `simulation.section.nav.${sub}` : "simulation.workspace.analysis")}</span>
                  <ChevronDown className="size-3 shrink-0" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {ANALYSIS_TABS.map((tab) => <DropdownMenuItem key={tab} onClick={() => goToTab(tab)}>{t(`simulation.section.nav.${tab}`)}</DropdownMenuItem>)}
              </DropdownMenuContent>
            </DropdownMenu>
          </nav>
        </div>

        <div className="min-h-0 flex-1 px-4 pb-4">
          <Outlet />
        </div>
      </div>
    </SimulationSectionContext.Provider>
  );
}
