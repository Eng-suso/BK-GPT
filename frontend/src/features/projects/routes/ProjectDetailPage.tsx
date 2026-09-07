import { useCallback, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Clock,
  FileText,
  MessageSquare,
  Pencil,
  Plus,
  Target,
} from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ProgressBar, NavRow, Meter } from "@/components/data";
import { EmptyState, ErrorState } from "@/components/feedback";
import { StatusIndicator } from "@/components/status";
import {
  DetailPanel,
  DetailPanelKeyValue,
  DetailPanelSection,
} from "@/components/panel";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import { ROUTES } from "@/app/routes";
import { cn } from "@/lib/utils";
import { ChatExperience } from "@/features/chat/ChatExperience";
import {
  useProjectQuery,
  useProjectSourcesQuery,
  useProjectDecisionsQuery,
} from "../api";
import { ProcessFormDialog } from "../components/ProcessFormDialog";
import { ProjectFormDialog } from "../components/ProjectFormDialog";
import {
  PROJECT_TABS,
  PROJECT_TAB_IDS,
  projectStatusTone,
  type Project,
  type ProjectProcess,
} from "../types";

/**
 * Displays the project detail workspace with project information, tabbed content, actions, and summary details.
 */
export function ProjectDetailPage(): React.JSX.Element {
  const { projectId = "" } = useParams();
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [formOpen, setFormOpen] = useState(false);
  // Nuova `key` a ogni apertura: il form riparte dal progetto appena caricato.
  const [formSession, setFormSession] = useState(0);
  const openForm = useCallback(() => {
    setFormSession((session) => session + 1);
    setFormOpen(true);
  }, []);
  // Il form processo: `null` crea, un processo modifica quel record.
  const [processOpen, setProcessOpen] = useState(false);
  const [editingProcess, setEditingProcess] = useState<ProjectProcess | null>(null);
  const [processSession, setProcessSession] = useState(0);
  const openProcessForm = useCallback((process: ProjectProcess | null) => {
    setEditingProcess(process);
    setProcessSession((session) => session + 1);
    setProcessOpen(true);
  }, []);

  const projectQ = useProjectQuery(projectId);
  const sourcesQ = useProjectSourcesQuery(projectId);
  const decisionsQ = useProjectDecisionsQuery(projectId);

  const tabParam = searchParams.get("tab") ?? "";
  const tab = PROJECT_TAB_IDS.includes(tabParam) ? tabParam : "overview";
  const setTab = useCallback(
    (next: string) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next === "overview") params.delete("tab");
          else params.set("tab", next);
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const goList = useCallback(
    () => navigate(ROUTES.projects.list),
    [navigate],
  );

  const openProcess = useCallback(
    (p: ProjectProcess) =>
      navigate(ROUTES.projects.process(projectId, p.id)),
    [navigate, projectId],
  );

  if (projectQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-80" />
        <Skeleton className="h-9 w-full max-w-lg" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (projectQ.isError || !projectQ.data) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorState
          description={t("state.loadError")}
          onRetry={() => void projectQ.refetch()}
          action={
            <Button variant="ghost" size="sm" onClick={goList}>
              {t("detail.backToList")}
            </Button>
          }
        />
      </div>
    );
  }

  const project = projectQ.data;
  const firstProcess = project.processItems[0];

  return (
    <div className={cn("grid h-full min-h-0 grid-cols-1", tab !== "chat" && "panel:grid-cols-[minmax(0,1fr)_var(--workspace-detail-panel)]")}>
      <div className={cn("flex min-h-0 min-w-0 flex-col bg-card", tab === "chat" ? "gap-2 overflow-hidden px-4 py-3" : "gap-4 overflow-auto px-7 py-6")}>
        <PageHeader
          compact={tab === "chat"}
          breadcrumbs={[
            { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
            { label: project.name },
          ]}
          title={project.name}
          meta={
            <>
              <span>{project.client}</span>
              <span aria-hidden>·</span>
              <StatusIndicator
                tone={projectStatusTone(project.status)}
                label={project.status}
              />
              <span aria-hidden>·</span>
              <span>
                {t("detail.phaseLabel")} {project.phase}
              </span>
            </>
          }
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={openForm}
              >
                <Pencil /> {t("detail.actions.edit")}
              </Button>
              {tab !== "chat" && <Button
                variant="outline"
                size="sm"
                onClick={() => setTab("chat")}
              >
                <MessageSquare /> {t("detail.actions.openChat")}
              </Button>}
              {firstProcess && (
                <Button size="sm" onClick={() => openProcess(firstProcess)}>
                  <ArrowRight /> {t("detail.actions.openProcess")}
                </Button>
              )}
            </>
          }
        />

        <Tabs
          value={tab}
          onValueChange={setTab}
          className={cn("flex min-w-0 flex-col gap-4", tab === "chat" && "min-h-0 flex-1")}
        >
          <div className={cn("min-w-0 shrink-0 overflow-x-auto pb-1", tab !== "chat" && "-mx-7 px-7")}>
            <TabsList variant="line" className="min-w-max">
              {PROJECT_TABS.map((tabDef) => (
                <TabsTrigger key={tabDef.id} value={tabDef.id}>
                  {t(tabDef.labelKey)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <TabsContent value="overview">
            <OverviewTab
              project={project}
              decisions={decisionsQ.data ?? []}
              onOpenProcess={openProcess}
              onEdit={openForm}
            />
          </TabsContent>
          <TabsContent value="chat" className="min-h-0 flex-1">
            <ProjectChatTab project={project} />
          </TabsContent>
          <TabsContent value="processes">
            <ProcessesTab
              processes={project.processItems}
              onOpenProcess={openProcess}
              onCreate={() => openProcessForm(null)}
              onEdit={openProcessForm}
            />
          </TabsContent>
          <TabsContent value="sources">
            <SimpleList
              items={(sourcesQ.data ?? []).map((s) => `${s.name} · ${s.type}`)}
              emptyTitle={t("detail.sources.empty")}
            />
          </TabsContent>
          <TabsContent value="decisions">
            <SimpleList
              items={(decisionsQ.data ?? []).map(
                (d) => `${d.title} · ${d.status}`,
              )}
              emptyTitle={t("detail.decisions.empty")}
            />
          </TabsContent>
        </Tabs>
      </div>

      <DetailPanel className={cn("hidden bg-card", tab !== "chat" && "panel:flex")}>
        <DetailPanelSection title={t("detail.panel.summary")}>
          <DetailPanelKeyValue
            rows={[
              { label: t("list.columns.phase"), value: project.phase },
              { label: t("detail.panel.nextStep"), value: project.nextStep },
              {
                label: t("list.columns.processes"),
                value: String(
                  project.processes || project.processItems.length,
                ),
              },
              {
                label: t("list.columns.progress"),
                value: <ProgressBar value={project.progress} width={72} />,
              },
            ]}
          />
        </DetailPanelSection>
        {project.milestones.length > 0 && (
          <DetailPanelSection title={t("detail.panel.milestones")}>
            <ul className="flex flex-col">
              {project.milestones.slice(0, 5).map((m, i) => (
                <li
                  key={m}
                  className="flex items-center gap-2 border-b border-border/60 py-2 text-xs text-foreground last:border-b-0"
                >
                  {i === 0 ? (
                    <CheckCircle2 className="size-4 flex-none text-[var(--color-status-success)]" />
                  ) : i === 1 ? (
                    <Clock className="size-4 flex-none text-[var(--color-status-warning)]" />
                  ) : (
                    <Circle className="size-4 flex-none text-muted-foreground" />
                  )}
                  {m}
                </li>
              ))}
            </ul>
          </DetailPanelSection>
        )}
      </DetailPanel>

      <ProjectFormDialog
        key={formSession}
        open={formOpen}
        onOpenChange={setFormOpen}
        project={project}
      />

      <ProcessFormDialog
        key={`process-${processSession}`}
        open={processOpen}
        onOpenChange={setProcessOpen}
        projectId={project.id}
        process={editingProcess}
      />
    </div>
  );
}

/**
 * Renders the project overview with its objective, processes, and decisions.
 *
 * @returns The project overview content.
 */

function OverviewTab({
  project,
  decisions,
  onOpenProcess,
  onEdit,
}: {
  project: Project;
  decisions: { title: string; status: string }[];
  onOpenProcess: (p: ProjectProcess) => void;
  onEdit: () => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  return (
    <div className="flex flex-col gap-6">
      <ObjectiveBlock objective={project.objective} onEdit={onEdit} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Block title={t("detail.overview.processes")}>
        {project.processItems.length === 0 ? (
          <EmptyState variant="inline" title={t("detail.processes.empty")} />
        ) : (
          project.processItems.slice(0, 5).map((p) => (
            <NavRow
              key={p.id}
              onClick={() => onOpenProcess(p)}
              className="px-0"
              title={p.name}
              meta={`${p.stage} · ${p.owner}`}
              trailing={
                <>
                  <Meter
                    value={p.readiness}
                    showValue={false}
                    height={4}
                    className="w-16"
                  />
                  <b className="text-xs tabular-nums text-foreground">
                    {Math.round(p.readiness / 10)}/10
                  </b>
                </>
              }
            />
          ))
        )}
      </Block>

      <Block title={t("detail.overview.decisions")}>
        {decisions.length === 0 ? (
          <EmptyState variant="inline" title={t("detail.decisions.empty")} />
        ) : (
          decisions.slice(0, 5).map((d) => (
            <div
              key={d.title}
              className="flex items-center gap-2 border-b border-border/60 py-2 text-xs text-foreground last:border-b-0"
            >
              {d.title}
              <span className="ml-auto text-micro text-muted-foreground">
                {d.status}
              </span>
            </div>
          ))
        )}
        </Block>
      </div>
    </div>
  );
}

/**
 * Displays the project objective and provides an action to add or edit it.
 *
 * @param objective - The project's objective text, or an empty string when no objective is set
 * @param onEdit - Called when the add or edit action is selected
 */
function ObjectiveBlock({
  objective,
  onEdit,
}: {
  objective: string;
  onEdit: () => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  return (
    <section className="flex flex-col rounded-xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="eyebrow flex items-center gap-1.5">
          <Target className="size-3.5" />
          {t("detail.overview.objective")}
        </h3>
        <Button
          variant="ghost"
          size="sm"
          className="-mt-1 h-7 px-2 text-xs"
          onClick={onEdit}
        >
          <Pencil /> {objective ? t("detail.actions.edit") : t("detail.objective.add")}
        </Button>
      </div>
      {objective ? (
        <p className="mt-2 max-w-[70ch] text-body-sm leading-relaxed text-foreground">
          {objective}
        </p>
      ) : (
        <p className="mt-2 max-w-[70ch] text-xs leading-relaxed text-muted-foreground">
          {t("detail.objective.empty")}
        </p>
      )}
    </section>
  );
}

/**
 * Renders the embedded chat experience for a project.
 *
 * @param project - Project whose chat context is displayed
 * @returns The project chat panel
 */
function ProjectChatTab({
  project,
}: {
  project: Project;
}): React.JSX.Element {
  return (
    // Chat surface. Fills the viewport below the app chrome (top bar + page
    // header + tab bar). A quiet slate hairline bounds it — the bare `<Card>`
    // `border` utility resolved to currentColor (near-black) under Tailwind v4
    // preflight; `border-border` pins it back to the subtle token.
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
      <ChatExperience
        chrome="panel"
        layout="embedded"
        scope={{
          type: "project",
          projectId: project.id,
          projectName: project.name,
        }}
      />
    </div>
  );
}

/**
 * Displays the project's processes with navigation, readiness, editing, and creation controls.
 *
 * @param processes - The processes to display
 * @param onOpenProcess - Called when a process is selected
 * @param onCreate - Called when the create-process action is selected
 * @param onEdit - Called when a process's edit action is selected
 */
function ProcessesTab({
  processes,
  onOpenProcess,
  onCreate,
  onEdit,
}: {
  processes: ProjectProcess[];
  onOpenProcess: (p: ProjectProcess) => void;
  onCreate: () => void;
  onEdit: (p: ProjectProcess) => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");

  const newProcessButton = (
    <Button size="sm" variant="outline" onClick={onCreate}>
      <Plus /> {t("process.actions.new")}
    </Button>
  );

  if (processes.length === 0) {
    return (
      <EmptyState
        variant="inline"
        title={t("detail.processes.empty")}
        description={t("process.empty.description")}
        action={newProcessButton}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Righe costruite a mano invece che con `NavRow`: aprire il processo e
          modificarne il record sono due intenzioni diverse, e servono due
          controlli fratelli — un bottone dentro un bottone non e' HTML valido
          e non riceverebbe il click. */}
      <ul className="flex flex-col rounded-xl border border-border bg-card">
        {processes.map((p) => (
          <li
            key={p.id}
            className="flex items-center gap-2 border-b border-border/60 px-4 py-2.5 last:border-b-0"
          >
            <button
              type="button"
              onClick={() => onOpenProcess(p)}
              className="flex min-w-0 flex-1 flex-col items-start rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <span className="truncate text-body-sm font-medium text-primary">
                {p.name}
              </span>
              <span className="truncate text-micro text-muted-foreground">
                {p.stage} · {p.status} · {p.owner}
              </span>
            </button>
            <Meter
              value={p.readiness}
              showValue={false}
              height={4}
              className="hidden w-16 flex-none sm:block"
            />
            <Button
              variant="ghost"
              size="sm"
              className="h-7 flex-none px-2 text-xs"
              aria-label={`${t("detail.actions.editProcess")}: ${p.name}`}
              onClick={() => onEdit(p)}
            >
              <Pencil /> {t("process.actions.edit")}
            </Button>
            <ArrowRight
              aria-hidden
              className="size-4 flex-none text-muted-foreground"
            />
          </li>
        ))}
      </ul>
      <div>{newProcessButton}</div>
    </div>
  );
}

function SimpleList({
  items,
  emptyTitle,
}: {
  items: string[];
  emptyTitle: string;
}): React.JSX.Element {
  if (items.length === 0) {
    return <EmptyState variant="inline" title={emptyTitle} />;
  }
  return (
    <ul className="flex flex-col rounded-xl border border-border bg-card">
      {items.map((item) => (
        <li
          key={item}
          className="flex items-center gap-2 border-b border-border/60 px-4 py-2 text-xs text-muted-foreground last:border-b-0"
        >
          <FileText className="size-3.5 flex-none" />
          {item}
        </li>
      ))}
    </ul>
  );
}

function Block({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section className="flex flex-col">
      <h3 className="eyebrow border-b border-border pb-2">{title}</h3>
      {children}
    </section>
  );
}
