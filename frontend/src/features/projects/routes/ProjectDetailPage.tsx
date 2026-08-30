import { useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, CheckCircle2, Circle, Clock, FileText } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ProgressBar } from "@/components/data";
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
import { cn } from "@/lib/utils";
import { ROUTES } from "@/app/routes";
import { ProcessWorkspace } from "@/features/process/ProcessWorkspace";
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
  const [openProcess, setOpenProcess] = useState<ProjectProcess | null>(null);

  const goList = useCallback(
    () => navigate(ROUTES.projects.list),
    [navigate],
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

  if (openProcess) {
    return (
      <ProcessWorkspace
        project={project}
        process={openProcess}
        onBack={() => setOpenProcess(null)}
      />
    );
  }

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

        {/* underline tabs */}
        <div
          role="tablist"
          className="flex gap-1 border-b border-border"
        >
          {PROJECT_TABS.map((tabDef) => (
            <button
              key={tabDef.id}
              role="tab"
              aria-selected={tab === tabDef.id}
              disabled={!tabDef.available}
              onClick={() => tabDef.available && setTab(tabDef.id)}
              className={cn(
                "-mb-px h-9 whitespace-nowrap border-b-2 border-transparent px-2.5 text-[13px] font-normal text-muted-foreground",
                tab === tabDef.id &&
                  "border-primary font-medium text-foreground",
                !tabDef.available && "opacity-40",
              )}
            >
              {t(tabDef.labelKey)}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <OverviewTab
            project={project}
            decisions={decisionsQ.data ?? []}
            onOpenProcess={setOpenProcess}
          />
        )}
        {tab === "processes" && (
          <ProcessesTab
            processes={project.processItems}
            onOpenProcess={setOpenProcess}
          />
        )}
        {tab === "sources" && (
          <SimpleList
            items={(sourcesQ.data ?? []).map((s) => `${s.name} · ${s.type}`)}
            emptyTitle={t("detail.sources.empty")}
          />
        )}
        {tab === "decisions" && (
          <SimpleList
            items={(decisionsQ.data ?? []).map(
              (d) => `${d.title} · ${d.status}`,
            )}
            emptyTitle={t("detail.decisions.empty")}
          />
        )}
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
            <button
              key={p.id}
              type="button"
              onClick={() => onOpenProcess(p)}
              className="flex w-full items-center justify-between gap-3 border-b border-border/60 py-2.5 text-left last:border-b-0"
            >
              <span>
                <span className="block text-[12.5px] font-medium text-foreground">
                  {p.name}
                </span>
                <span className="text-[11.5px] text-muted-foreground">
                  {p.stage} · {p.owner}
                </span>
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="block h-1 w-14 overflow-hidden rounded-full bg-[var(--slate-200)]">
                  <span
                    className="block h-full rounded-full bg-primary"
                    style={{ width: `${p.readiness}%` }}
                  />
                </span>
                <b className="text-[11.5px] tabular-nums text-foreground">
                  {Math.round(p.readiness / 10)}/10
                </b>
              </span>
            </button>
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
        <button
          key={p.id}
          type="button"
          onClick={() => onOpenProcess(p)}
          className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3 text-left last:border-b-0 hover:bg-muted/40"
        >
          <span>
            <span className="block text-[13px] font-medium text-primary">
              {p.name}
            </span>
            <span className="text-[11.5px] text-muted-foreground">
              {p.stage} · {p.owner}
            </span>
          </span>
          <ArrowRight className="size-4 text-muted-foreground" />
        </button>
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
