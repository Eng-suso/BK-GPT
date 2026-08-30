import { useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, CheckCircle2, Circle, Clock, FileText } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ProgressBar, NavRow } from "@/components/data";
import { EmptyState, ErrorState } from "@/components/feedback";
import { StatusIndicator } from "@/components/status";
import {
  DetailPanel,
  DetailPanelHeader,
  DetailPanelKeyValue,
  DetailPanelSection,
} from "@/components/panel";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import { ROUTES } from "@/app/routes";
import {
  useProjectQuery,
  useProjectSourcesQuery,
  useProjectDecisionsQuery,
} from "../api";
import {
  PROJECT_TABS,
  projectStatusTone,
  type Project,
  type ProjectProcess,
} from "../types";

export function ProjectDetailPage(): React.JSX.Element {
  const { projectId = "" } = useParams();
  const { t } = useTranslation("projects");
  const navigate = useNavigate();

  const projectQ = useProjectQuery(projectId);
  const sourcesQ = useProjectSourcesQuery(projectId);
  const decisionsQ = useProjectDecisionsQuery(projectId);

  const [tab, setTab] = useState("overview");

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

  return (
    <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-4 overflow-auto bg-card px-7 py-6">
        <PageHeader
          breadcrumbs={[
            { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
            { label: project.name },
          ]}
          title={project.name}
          actions={
            <>
              <Button variant="ghost" size="sm">
                {t("detail.actions.updateStatus")}
              </Button>
              <Button size="sm">
                <ArrowRight /> {t("detail.actions.openRoadmap")}
              </Button>
            </>
          }
        />
        <p className="-mt-2 flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>{project.client}</span>
          <span>·</span>
          <StatusIndicator
            tone={projectStatusTone(project.status)}
            label={project.status}
          />
          <span>·</span>
          <span>
            {t("detail.phaseLabel")} {project.phase}
          </span>
        </p>

        <Tabs
          value={tab}
          onValueChange={setTab}
          className="flex flex-col gap-4"
        >
          <TabsList variant="line">
            {PROJECT_TABS.map((tabDef) => (
              <TabsTrigger
                key={tabDef.id}
                value={tabDef.id}
                disabled={!tabDef.available}
              >
                {t(tabDef.labelKey)}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="overview">
            <OverviewTab
              project={project}
              decisions={decisionsQ.data ?? []}
              onOpenProcess={openProcess}
            />
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

      <DetailPanel className="hidden bg-card xl:flex">
        <DetailPanelHeader title={project.name} subtitle={project.client} />
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
                  className="flex items-center gap-2.5 border-b border-border/60 py-2 text-[12.5px] text-foreground last:border-b-0"
                >
                  {i === 0 ? (
                    <CheckCircle2 className="size-[15px] flex-none text-[var(--color-status-success)]" />
                  ) : i === 1 ? (
                    <Clock className="size-[15px] flex-none text-[var(--color-status-warning)]" />
                  ) : (
                    <Circle className="size-[15px] flex-none text-muted-foreground" />
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
    <div className="grid grid-cols-2 gap-6">
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
                  <span className="block h-1 w-14 overflow-hidden rounded-full bg-[var(--slate-200)]">
                    <span
                      className="block h-full rounded-full bg-primary"
                      style={{ width: `${p.readiness}%` }}
                    />
                  </span>
                  <b className="text-[11.5px] tabular-nums text-foreground">
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
              className="flex items-center gap-2.5 border-b border-border/60 py-2.5 text-[12.5px] text-foreground last:border-b-0"
            >
              {d.title}
              <span className="ml-auto text-[11px] text-muted-foreground">
                {d.status}
              </span>
            </div>
          ))
        )}
      </Block>

      <Block title={t("detail.overview.kpi")}>
        <EmptyState
          variant="inline"
          title={t("detail.unavailable.title")}
          description={t("detail.unavailable.kpi")}
        />
      </Block>
      <Block title={t("detail.overview.team")}>
        <EmptyState
          variant="inline"
          title={t("detail.unavailable.title")}
          description={t("detail.unavailable.team")}
        />
      </Block>
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
          titleClassName="text-[13px] text-primary"
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
          className="flex items-center gap-2.5 border-b border-border/60 px-4 py-2.5 text-[12.5px] text-muted-foreground last:border-b-0"
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
      <h3 className="border-b border-border pb-2.5 text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}
