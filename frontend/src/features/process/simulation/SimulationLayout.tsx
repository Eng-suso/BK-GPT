import React from "react";
import {
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  Columns2,
  Flame,
  LayoutGrid,
  Play,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

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
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { ROUTES } from "@/app/routes";
import { useProjectQuery } from "@/features/projects/api";

import { useBpmnModelQuery } from "../api";
import { listProsimosSimulationRuns } from "./simulationApi";
import { SimulationSectionContext } from "./useSimulationSection";

type NavItem = {
  key: string;
  icon: LucideIcon;
  /** Route carries the active run id (…/replay/:runId). */
  runScoped?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { key: "overview", icon: LayoutGrid },
  { key: "scenario", icon: SlidersHorizontal },
  { key: "replay", icon: Play, runScoped: true },
  { key: "dashboard", icon: Activity, runScoped: true },
  { key: "compare", icon: Columns2 },
  { key: "heatmap", icon: Flame, runScoped: true },
  { key: "insights", icon: Sparkles, runScoped: true },
];

/** Pull `<sub>` and optional numeric `<runId>` out of …/simulation/<sub>/<runId>. */
function readPath(pathname: string): { sub: string; runId: number | null } {
  const parts = pathname.split("/").filter(Boolean);
  const idx = parts.indexOf("simulation");
  const sub = (idx >= 0 && parts[idx + 1]) || "overview";
  const raw = idx >= 0 ? parts[idx + 2] : undefined;
  const runId = raw && /^\d+$/.test(raw) ? Number(raw) : null;
  return { sub, runId };
}

export function SimulationLayout(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const location = useLocation();
  const stacked = useMediaQuery("(max-width: 1023px)");

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

  if (projectQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6">
        <Skeleton className="h-4 w-56" />
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    );
  }

  if (projectQ.isError || !project || !process) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorState
          description={
            projectQ.isError
              ? t("state.loadError")
              : t("state.processNotFound")
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

  const hrefFor = (item: NavItem) =>
    ROUTES.projects.simulation(
      projectId,
      processId,
      item.runScoped && activeRunId != null
        ? `${item.key}/${activeRunId}`
        : item.key,
    );

  const onSwitchRun = (value: string) => {
    const target = NAV_ITEMS.find((i) => i.key === sub)?.runScoped ? sub : "replay";
    navigate(
      ROUTES.projects.simulation(projectId, processId, `${target}/${value}`),
    );
  };

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

  const nav = (
    <nav
      aria-label={t("simulation.section.navLabel")}
      className={cn(
        "gap-1",
        stacked
          ? "flex overflow-x-auto border-b border-border px-4 py-2"
          : "flex flex-col border-r border-border p-2",
      )}
    >
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.key}
            to={hrefFor(item)}
            className={({ isActive }) =>
              cn(
                "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "text-muted-foreground hover:bg-muted hover:text-foreground",
                (isActive || sub === item.key) &&
                  "bg-muted text-foreground",
              )
            }
          >
            <Icon aria-hidden className="size-4 shrink-0" />
            <span className={stacked ? "" : "truncate"}>
              {t(`simulation.section.nav.${item.key}`)}
            </span>
          </NavLink>
        );
      })}
    </nav>
  );

  return (
    <SimulationSectionContext.Provider value={contextValue}>
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex flex-col gap-3 border-b border-border px-7 pb-3 pt-5">
          <nav aria-label="Breadcrumb">
            <ol className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <li>
                <NavLink to={ROUTES.projects.list} className="hover:text-foreground">
                  {t("breadcrumb.projects")}
                </NavLink>
              </li>
              <li aria-hidden>/</li>
              <li>
                <NavLink
                  to={ROUTES.projects.detail(project.id)}
                  className="hover:text-foreground"
                >
                  {project.name}
                </NavLink>
              </li>
              <li aria-hidden>/</li>
              <li>
                <NavLink
                  to={ROUTES.projects.process(project.id, process.id)}
                  className="hover:text-foreground"
                >
                  {process.name}
                </NavLink>
              </li>
              <li aria-hidden>/</li>
              <li className="text-foreground/80">
                {t("simulation.section.title")}
              </li>
            </ol>
          </nav>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-baseline gap-2.5">
              <h1 className="text-xl font-semibold tracking-[-0.02em] text-foreground">
                {t("simulation.section.title")}
              </h1>
              <span className="text-sm text-muted-foreground">{process.name}</span>
            </div>

            <div className="flex items-center gap-2">
              {runs.length > 0 && (
                <Select
                  value={activeRunId != null ? String(activeRunId) : undefined}
                  onValueChange={onSwitchRun}
                >
                  <SelectTrigger size="sm" className="w-[220px]">
                    <SelectValue
                      placeholder={t("simulation.section.runSwitcher")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {runs.map((run) => (
                      <SelectItem key={run.id} value={String(run.id)}>
                        {run.scenario_name}
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
          </div>
        </header>

        <div
          className={cn(
            "min-h-0 flex-1",
            stacked ? "flex flex-col" : "grid grid-cols-[196px_minmax(0,1fr)]",
          )}
        >
          {nav}
          <div className="min-h-0 min-w-0 overflow-hidden">
            <Outlet />
          </div>
        </div>
      </div>
    </SimulationSectionContext.Provider>
  );
}
