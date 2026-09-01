import { useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Clock,
  FileText,
  MessageSquare,
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
import { ChatExperience } from "@/features/chat/ChatExperience";
import {
  useProjectQuery,
  useProjectSourcesQuery,
  useProjectDecisionsQuery,
} from "../api";
import {
  PROJECT_TABS,
  PROJECT_TAB_IDS,
  projectStatusTone,
  type Project,
  type ProjectProcess,
} from "../types";

export function ProjectDetailPage(): React.JSX.Element {
  const { projectId = "" } = useParams();
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

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
    <div className="grid h-full min-h-0 grid-cols-1 panel:grid-cols-[minmax(0,1fr)_var(--workspace-detail-panel)]">
      <div className="flex min-w-0 flex-col gap-4 overflow-auto bg-card px-7 py-6">
        <PageHeader
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
                onClick={() => setTab("chat")}
              >
                <MessageSquare /> {t("detail.actions.openChat")}
              </Button>
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
          className="flex min-w-0 flex-col gap-4"
        >
          <div className="-mx-7 min-w-0 overflow-x-auto px-7 pb-1">
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
            />
          </TabsContent>
          <TabsContent value="chat" className="min-h-0">
            <ProjectChatTab project={project} />
          </TabsContent>
          <TabsContent value="processes">
            <ProcessesTab
              processes={project.processItems}
              onOpenProcess={openProcess}
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

      <DetailPanel className="hidden bg-card panel:flex">
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
    </div>
  );
}

/* ------------------------------------------------------------------ */

function OverviewTab({
  project,
  decisions,
  onOpenProcess,
}: {
  project: Project;
  decisions: { title: string; status: string }[];
  onOpenProcess: (p: ProjectProcess) => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  return (
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
  );
}

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
    <div className="flex h-[calc(100dvh-16rem)] min-h-[32rem] w-full min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
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

function ProcessesTab({
  processes,
  onOpenProcess,
}: {
  processes: ProjectProcess[];
  onOpenProcess: (p: ProjectProcess) => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  if (processes.length === 0) {
    return <EmptyState variant="inline" title={t("detail.processes.empty")} />;
  }
  return (
    <div className="flex flex-col rounded-xl border border-border bg-card">
      {processes.map((p) => (
        <NavRow
          key={p.id}
          onClick={() => onOpenProcess(p)}
          className="py-3"
          titleClassName="text-body-sm text-primary"
          title={p.name}
          meta={`${p.stage} · ${p.owner}`}
          trailing={<ArrowRight className="size-4 text-muted-foreground" />}
        />
      ))}
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
