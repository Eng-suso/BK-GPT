import { useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/ui/tabs";
import { ROUTES } from "@/app/routes";
import { useProjectQuery } from "@/features/projects/api";
import { ProcessWorkspace, type ProcessView } from "../ProcessWorkspace";

const VIEWS: ProcessView[] = ["canvas", "chat", "simulation"];

function parseView(raw: string | null): ProcessView {
  // Back-compat: the old standalone "properties" view is now a canvas dock.
  if (raw === "properties") return "canvas";
  return VIEWS.includes(raw as ProcessView) ? (raw as ProcessView) : "canvas";
}

export function ProcessStudioPage(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const projectQ = useProjectQuery(projectId);
  const rawView = searchParams.get("view");
  const view = parseView(rawView);
  const propertiesOpen =
    view === "canvas" &&
    (searchParams.get("panel") === "properties" || rawView === "properties");

  const setView = useCallback(
    (next: string) => {
      setSearchParams(
        (prev) => {
          const sp = new URLSearchParams(prev);
          sp.set("view", next);
          return sp;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const togglePropertiesPanel = useCallback(() => {
    setSearchParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        sp.set("view", "canvas");
        if (sp.get("panel") === "properties") sp.delete("panel");
        else sp.set("panel", "properties");
        return sp;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  const backToProject = useCallback(
    () => navigate(ROUTES.projects.detail(projectId)),
    [navigate, projectId],
  );

  if (projectQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6">
        <Skeleton className="h-4 w-56" />
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    );
  }

  const project = projectQ.data;
  const process = project?.processItems.find((p) => p.id === processId);

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
            <Button variant="ghost" size="sm" onClick={backToProject}>
              {t("actions.backToProject")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 px-7 pb-2 pt-6">
        <PageHeader
          breadcrumbs={[
            { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
            { label: project.name, to: ROUTES.projects.detail(project.id) },
            { label: process.name },
          ]}
          title={process.name}
          actions={
            <Button variant="ghost" size="sm" onClick={backToProject}>
              {t("actions.backToProject")}
            </Button>
          }
        />
        <Tabs value={view} onValueChange={setView}>
          <TabsList variant="line">
            {VIEWS.map((v) => (
              <TabsTrigger key={v} value={v}>
                {t(`tabs.${v}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="min-h-0 flex-1">
        <ProcessWorkspace
          project={project}
          process={process}
          view={view}
          propertiesOpen={propertiesOpen}
          onTogglePropertiesPanel={togglePropertiesPanel}
        />
      </div>
    </div>
  );
}
