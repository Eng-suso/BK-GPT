import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/layout";
import { NavRow } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import { EmptyState, ErrorState } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";
import { ROUTES } from "@/app/routes";
import { useWorkspaceRefresh } from "@/lib/hooks/useWorkspaceRefresh";
// Home is an aggregation dashboard; importing the projects/clients query hooks
// is a deliberate exception to the no-cross-feature-import rule.
import { useProjectsQuery } from "@/features/projects/api";
import { projectStatusTone } from "@/features/projects/types";
import { useClientsQuery } from "@/features/clients/api";
import { clientStatusTone } from "@/features/clients/types";

export function HomePage(): React.JSX.Element {
  const { t } = useTranslation("common");
  useWorkspaceRefresh();

  const projectsQ = useProjectsQuery();
  const clientsQ = useClientsQuery();

  const projects = useMemo(() => projectsQ.data ?? [], [projectsQ.data]);
  const clients = useMemo(() => clientsQ.data ?? [], [clientsQ.data]);
  const isLoading = projectsQ.isLoading || clientsQ.isLoading;
  const isError = projectsQ.isError || clientsQ.isError;

  const processCount = useMemo(
    () => projects.reduce((sum, p) => sum + (p.processes || 0), 0),
    [projects],
  );

  const metrics = [
    { key: "clients", value: clients.length },
    { key: "projects", value: projects.length },
    { key: "processes", value: processCount },
  ];

  return (
    <div className="flex h-full flex-col gap-5 overflow-auto px-7 py-6">
      <PageHeader
        breadcrumbs={[{ label: t("nav.home") }]}
        title={t("nav.home")}
        description={t("home.description")}
      />

      {isError ? (
        <div className="flex flex-1 items-center justify-center rounded-xl border border-border bg-card">
          <ErrorState onRetry={() => void projectsQ.refetch()} />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            {metrics.map((m) => (
              <div
                key={m.key}
                className="rounded-xl border border-border bg-card p-4 shadow-[0_1px_3px_rgba(14,20,32,0.06)]"
              >
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">
                  {t(`home.metrics.${m.key}`)}
                </div>
                <div className="mt-2 text-2xl font-semibold tabular-nums tracking-[-0.02em]">
                  {isLoading ? (
                    <Skeleton className="h-7 w-10" />
                  ) : (
                    m.value
                  )}
                </div>
                <div className="mt-1.5 text-[11.5px] text-muted-foreground">
                  {t(`home.metrics.${m.key}Note`)}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <HomeList
              title={t("nav.projects")}
              seeAllTo={ROUTES.projects.list}
              seeAllLabel={t("home.seeAll")}
              loading={isLoading}
              emptyLabel={t("home.emptyProjects")}
              items={projects.slice(0, 6).map((p) => ({
                id: p.id,
                to: ROUTES.projects.detail(p.id),
                title: p.name,
                meta: `${p.client} · ${p.phase}`,
                tone: projectStatusTone(p.status),
                status: p.status,
              }))}
            />
            <HomeList
              title={t("nav.clients")}
              seeAllTo={ROUTES.clients.list}
              seeAllLabel={t("home.seeAll")}
              loading={isLoading}
              emptyLabel={t("home.emptyClients")}
              items={clients.slice(0, 6).map((c) => ({
                id: c.id,
                to: ROUTES.clients.list,
                title: c.name,
                meta: c.nextActivity,
                tone: clientStatusTone(c.status),
                status: c.status,
              }))}
            />
          </div>
        </>
      )}
    </div>
  );
}

type HomeListItem = {
  id: string;
  to: string;
  title: string;
  meta: string;
  tone: React.ComponentProps<typeof StatusIndicator>["tone"];
  status: string;
};

function HomeList({
  title,
  seeAllTo,
  seeAllLabel,
  loading,
  emptyLabel,
  items,
}: {
  title: string;
  seeAllTo: string;
  seeAllLabel: string;
  loading: boolean;
  emptyLabel: string;
  items: HomeListItem[];
}): React.JSX.Element {
  return (
    <section className="flex flex-col rounded-xl border border-border bg-card shadow-[0_1px_3px_rgba(14,20,32,0.06)]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground">
          {title}
        </h3>
        <Link to={seeAllTo} className="text-[12px] font-medium text-primary hover:text-primary/85">
          {seeAllLabel}
        </Link>
      </div>
      {loading ? (
        <div className="flex flex-col gap-2 p-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState variant="inline" title={emptyLabel} className="px-4" />
      ) : (
        <ul className="flex flex-col">
          {items.map((item) => (
            <li key={item.id}>
              <NavRow
                to={item.to}
                title={item.title}
                meta={item.meta}
                trailing={
                  <StatusIndicator tone={item.tone} label={item.status} />
                }
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
