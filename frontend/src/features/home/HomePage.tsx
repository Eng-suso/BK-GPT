import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Building2, FolderKanban, Workflow } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { NavRow } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import { EmptyState, ErrorState } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";
import { ROUTES } from "@/app/routes";
// Home is an aggregation dashboard; importing the projects/clients query hooks
// is a deliberate exception to the no-cross-feature-import rule.
import { useProjectsQuery } from "@/features/projects/api";
import { projectStatusTone } from "@/features/projects/types";
import { useClientsQuery } from "@/features/clients/api";
import { usePeriod } from "@/features/period/usePeriod";
import { overlapsPeriod } from "@/features/period/periods";
import { clientStatusTone } from "@/features/clients/types";

export function HomePage(): React.JSX.Element {
  const { t } = useTranslation("common");

  const projectsQ = useProjectsQuery();
  const clientsQ = useClientsQuery();
  const { period, range } = usePeriod();

  // I numeri della home sono quelli del periodo scelto nella barra: mostrarne
  // altri accanto a un intervallo li renderebbe sbagliati anche se giusti.
  const projects = useMemo(
    () => (projectsQ.data ?? []).filter((project) => overlapsPeriod(project, range)),
    [projectsQ.data, range],
  );
  // I clienti seguono i progetti del periodo: un riquadro filtrato accanto a
  // uno che conta tutto racconta due storie nella stessa schermata.
  const clients = useMemo(() => {
    const all = clientsQ.data ?? [];
    if (period === "all") return all;
    // Per id e non per nome: due clienti possono chiamarsi uguale, e un nome
    // cambiato smetterebbe di corrispondere.
    const inPeriod = new Set(projects.map((project) => project.clientId));
    return all.filter((client) => inPeriod.has(client.id));
  }, [clientsQ.data, projects, period]);
  const isLoading = projectsQ.isLoading || clientsQ.isLoading;
  const isError = projectsQ.isError || clientsQ.isError;

  const processCount = useMemo(
    () => projects.reduce((sum, p) => sum + (p.processes || 0), 0),
    [projects],
  );

  const metrics = [
    { key: "clients", value: clients.length, icon: Building2 },
    { key: "projects", value: projects.length, icon: FolderKanban },
    { key: "processes", value: processCount, icon: Workflow },
  ];

  return (
    <div className="ui-scrollbar h-full overflow-auto px-4 py-6 sm:px-7 sm:py-8 lg:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-7">
      <PageHeader
        breadcrumbs={[{ label: t("nav.home") }]}
        title={t("nav.home")}
        description={
          period === "all"
            ? t("home.description")
            : `${t("home.description")} · ${t("period.scoped", { period: t(`period.${period}`) })}`
        }
      />

      {isError ? (
        <div className="flex flex-1 items-center justify-center ui-surface ui-surface-panel">
          <ErrorState onRetry={() => { void projectsQ.refetch(); void clientsQ.refetch(); }} />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            {metrics.map((m) => (
              <div
                key={m.key}
                className="ui-surface ui-surface-panel flex min-w-0 items-start justify-between gap-4 p-3 sm:p-5"
              >
                <div>
                <div className="text-xs font-medium text-muted-foreground sm:text-body-sm">
                  {t(`home.metrics.${m.key}`)}
                </div>
                <div className="mt-2 text-2xl font-semibold tabular-nums tracking-[-0.04em] sm:text-3xl">
                  {isLoading ? (
                    <Skeleton className="h-7 w-10" />
                  ) : (
                    m.value
                  )}
                </div>
                <div className="mt-2 hidden text-xs leading-5 text-muted-foreground sm:block">
                  {t(`home.metrics.${m.key}Note`)}
                </div>
                </div>
                <m.icon className="mt-0.5 hidden size-[18px] shrink-0 text-muted-foreground sm:block" strokeWidth={1.6} aria-hidden="true" />
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
                meta: p.nextStep ? `${p.client} · ${p.nextStep}` : `${p.client} · ${p.phase}`,
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
    <section className="ui-surface ui-surface-panel min-w-0 overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <Link to={seeAllTo} className="inline-flex min-h-8 shrink-0 items-center gap-1 rounded-md text-xs font-medium text-primary outline-none hover:underline focus-visible:outline-2 focus-visible:outline-ring">
          {seeAllLabel}
          <ArrowUpRight className="size-3.5" aria-hidden="true" />
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
