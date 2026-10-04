import { useCallback } from "react";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FlaskConical, ArrowLeft, Users, MessagesSquare, Workflow } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { Surface } from "@/ui/surface";
import { Badge } from "@/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/ui/tabs";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { ROUTES } from "@/app/routes";
import { useProjectQuery } from "@/features/projects/api";
import type { ProjectProcess } from "@/contracts/workspace";
import { ProcessWorkspace, type ProcessView } from "../ProcessWorkspace";

// Le chiavi sono il vocabolario degli stati che arriva dal backend
// (`backend/workspace_defaults.py`), non testo da leggere: restano in italiano
// anche quando l'interfaccia e' in inglese, perche' sono valori, non parole.
const PROCESS_STATUS_TONE: Record<ProjectProcess["status"], StatusTone> = {
  "In corso": "ok",
  "Da validare": "pending",
  Validato: "ok",
  Bozza: "neutral",
};

// Discussion leads (chat-driven modelling), then the model. Simulation is its
// own section now, reached from the header button; `?view=simulation` redirects.
const VIEWS: ProcessView[] = ["chat", "canvas"];

function parseView(raw: string | null): ProcessView {
  // Back-compat: the old standalone "properties" view is now a canvas dock.
  if (raw === "properties") return "canvas";
  // Senza `?view` si apre la discussione, non il canvas: aprire un processo
  // significa riprendere il filo con l'agente, e il modello e' il risultato di
  // quella conversazione. Chi vuole il canvas ci arriva con un click, e il link
  // con `?view=canvas` continua ad aprirlo direttamente.
  return VIEWS.includes(raw as ProcessView) ? (raw as ProcessView) : "chat";
}

/**
 * Renders the process studio with chat and canvas views.
 *
 * @returns The process studio page element.
 */
export function ProcessStudioPage(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const projectQ = useProjectQuery(projectId);
  const rawView = searchParams.get("view");
  const view = parseView(rawView);
  // Simulation moved to its own section — keep old `?view=simulation` links working.
  const redirectToSimulation = rawView === "simulation";
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

  if (redirectToSimulation) {
    return (
      <Navigate
        to={ROUTES.projects.simulation(projectId, processId)}
        replace
      />
    );
  }

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
    <Tabs value={view} onValueChange={setView} className="h-full min-h-0 gap-0">
      <Surface variant="chrome" className="process-studio-header mx-4 mb-3 mt-3 flex shrink-0 flex-col gap-3 rounded-xl p-4">
        <PageHeader
          compact
          className="[&_h1]:text-xl"
          breadcrumbs={[
            { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
            { label: project.name, to: ROUTES.projects.detail(project.id) },
            { label: process.name },
          ]}
          title={process.name}
          meta={
            <>
              <StatusIndicator
                tone={PROCESS_STATUS_TONE[process.status] ?? "neutral"}
                label={process.status}
              />
              <Badge variant="secondary">{process.stage}</Badge>
              <span className="inline-flex min-w-0 items-center gap-1.5" title={`${t("side.summary.ownerLabel")}: ${process.owner}`}><Users aria-hidden className="size-3.5 shrink-0" /><span className="break-words">{process.owner}</span></span>
              <Badge variant="outline" className="tabular-nums">{t("side.summary.readiness")} {process.readiness}%</Badge>
            </>
          }
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  navigate(
                    ROUTES.projects.simulation(project.id, process.id),
                  )
                }
              >
                <FlaskConical aria-hidden className="size-4" />
                {t("simulation.section.title")}
              </Button>
              <Button variant="ghost" size="sm" onClick={backToProject}>
                <ArrowLeft aria-hidden className="size-4" />{t("actions.backToProject")}
              </Button>
            </>
          }
        />
        <TabsList aria-label={t("actions.views")}>
          {VIEWS.map((v) => <TabsTrigger key={v} value={v}>{v === "chat" ? <MessagesSquare aria-hidden /> : <Workflow aria-hidden />}{t(`tabs.${v}`)}</TabsTrigger>)}
        </TabsList>
      </Surface>

      <TabsContent value={view} className="min-h-0 flex-1">
        <ProcessWorkspace
          project={project}
          process={process}
          view={view}
          propertiesOpen={propertiesOpen}
          onTogglePropertiesPanel={togglePropertiesPanel}
          onOpenDiscussion={() => setView("chat")}
        />
      </TabsContent>
    </Tabs>
  );
}
